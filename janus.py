import argparse
import asyncio
import logging
import random
import string
import time

import aiohttp

from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaPlayer, MediaRecorder

from av.frame import Frame
import fractions
from typing import Tuple

AUDIO_PTIME = 0.020  # 20ms audio packetization
VIDEO_CLOCK_RATE = 90000
VIDEO_PTIME = 1 / 30  # 30fps
VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)


class MediaStreamError(Exception):
	pass


class MyvideoStreamTrack(VideoStreamTrack):
	kind = "video"

	_start: float
	_timestamp: int

	async def recv(self) -> Frame:

		kind = "video"

		_start: float
		_timestamp: int

	async def next_timestamp(self) -> Tuple[int, fractions.Fraction]:
		if self.readyState != "live":
			raise MediaStreamError

		if hasattr(self, "_timestamp"):
			self._timestamp += int(VIDEO_PTIME * VIDEO_CLOCK_RATE)
			wait = self._start + (self._timestamp / VIDEO_CLOCK_RATE) - time.time()
			await asyncio.sleep(wait)
		else:
			self._start = time.time()
			self._timestamp = 0
		return self._timestamp, VIDEO_TIME_BASE

	"""
	Receive the next :class:`~av.video.frame.VideoFrame`.

	The base implementation just reads a 640x480 green frame at 30fps,
	subclass :class:`VideoStreamTrack` to provide a useful implementation.
	"""

	async def recv(self) -> Frame:
		pts, time_base = await self.next_timestamp()
		for p in frame.planes:
			p.update(bytes(p.buffer_size))
		frame.pts = pts
		frame.time_base = time_base
		return frame


pcs = set()


def transaction_id():
	return "".join(random.choice(string.ascii_letters) for x in range(12))


class JanusPlugin:
	def __init__(self, session, url):
		self._queue = asyncio.Queue()
		self._session = session
		self._url = url

	async def send(self, payload):
		message = {"janus": "message", "transaction": transaction_id()}
		message.update(payload)
		async with self._session._http.post(self._url, json=message) as response:
			data = await response.json()
			assert data["janus"] == "ack"

		response = await self._queue.get()
		assert response["transaction"] == message["transaction"]
		return response


class JanusSession:
	def __init__(self, url):
		self._http = None
		self._poll_task = None
		self._plugins = {}
		self._root_url = url
		self._session_url = None

	async def attach(self, plugin_name: str) -> JanusPlugin:
		message = {
			"janus": "attach",
			"plugin": plugin_name,
			"transaction": transaction_id(),
		}
		async with self._http.post(self._session_url, json=message) as response:
			data = await response.json()
			assert data["janus"] == "success"
			plugin_id = data["data"]["id"]
			plugin = JanusPlugin(self, self._session_url + "/" + str(plugin_id))
			self._plugins[plugin_id] = plugin
			return plugin

	async def create(self):
		self._http = aiohttp.ClientSession()
		message = {"janus": "create", "transaction": transaction_id()}
		async with self._http.post(self._root_url, json=message) as response:
			data = await response.json()
			assert data["janus"] == "success"
			session_id = data["data"]["id"]
			self._session_url = self._root_url + "/" + str(session_id)

		self._poll_task = asyncio.ensure_future(self._poll())

	async def destroy(self):
		if self._poll_task:
			self._poll_task.cancel()
			self._poll_task = None

		if self._session_url:
			message = {"janus": "destroy", "transaction": transaction_id()}
			async with self._http.post(self._session_url, json=message) as response:
				data = await response.json()
				assert data["janus"] == "success"
			self._session_url = None

		if self._http:
			await self._http.close()
			self._http = None

	async def _poll(self):
		while True:
			params = {"maxev": 1, "rid": int(time.time() * 1000)}
			async with self._http.get(self._session_url, params=params) as response:
				data = await response.json()
				if data["janus"] == "event":
					plugin = self._plugins.get(data["sender"], None)
					if plugin:
						await plugin._queue.put(data)
					else:
						print(data)


async def publish(plugin, player):
	"""
	Send video to the room.
	"""
	# player = MediaPlayer('/home/pi/my_project/car.MP4')
	player = MediaPlayer('/dev/video0', format='v4l2', options={
		'video_size': '320x240'
	})

	pc = RTCPeerConnection()
	pcs.add(pc)

	# configure media
	media = {"audio": False, "video": True}
	if player and player.audio:
		pc.addTrack(player.audio)
		media["audio"] = True

	if player and player.video:
		pc.addTrack(player.video)
		time.sleep(0.01)
	# else:
	# pc.addTrack(VideoStreamTrack())

	# send offer
	await pc.setLocalDescription(await pc.createOffer())
	request = {"request": "configure"}
	request.update(media)
	response = await plugin.send(
		{
			"body": request,
			"jsep": {
				"sdp": pc.localDescription.sdp,
				"trickle": False,
				"type": pc.localDescription.type,
			},
		}
	)

	# apply answer
	await pc.setRemoteDescription(
		RTCSessionDescription(
			sdp=response["jsep"]["sdp"], type=response["jsep"]["type"]
		)
	)


async def subscribe(session, room, feed, recorder):
	pc = RTCPeerConnection()
	pcs.add(pc)

	@pc.on("track")
	async def on_track(track):
		print("Track %s received" % track.kind)
		if track.kind == "video":
			recorder.addTrack(track)
		if track.kind == "audio":
			recorder.addTrack(track)

	# subscribe
	plugin = await session.attach("janus.plugin.videoroom")
	response = await plugin.send(
		{"body": {"request": "join", "ptype": "subscriber", "room": room, "feed": feed}}
	)

	# apply offer
	await pc.setRemoteDescription(
		RTCSessionDescription(
			sdp=response["jsep"]["sdp"], type=response["jsep"]["type"]
		)
	)

	# send answer
	await pc.setLocalDescription(await pc.createAnswer())
	response = await plugin.send(
		{
			"body": {"request": "start"},
			"jsep": {
				"sdp": pc.localDescription.sdp,
				"trickle": False,
				"type": pc.localDescription.type,
			},
		}
	)
	await recorder.start()


async def run(player, recorder, room, session):
	await session.create()

	# join video room
	plugin = await session.attach("janus.plugin.videoroom")
	response = await plugin.send(
		{
			"body": {
				"display": "aiortc",
				"ptype": "publisher",
				"request": "join",
				"room": room,
			}
		}
	)
	publishers = response["plugindata"]["data"]["publishers"]
	for publisher in publishers:
		print("id: %(id)s, display: %(display)s" % publisher)
	await publish(plugin=plugin, player=player)
	if recorder is not None and publishers:
		await subscribe(
			session=session, room=room, feed=publishers[0]["id"], recorder=recorder
		)

	# exchange media for 10 minutes
	print("Exchanging media")
	await asyncio.sleep(600)


if __name__ == "__main__":
	session = JanusSession("http://1.15.156.106:8088/janus")
	player = None
	recorder = None
	room = 1234
	loop = asyncio.get_event_loop()
	try:
		loop.run_until_complete(
			run(player=player, recorder=recorder, room=room, session=session)
		)
	except KeyboardInterrupt:
		pass
	finally:
		if recorder is not None:
			loop.run_until_complete(recorder.stop())
		loop.run_until_complete(session.destroy())
		coros = [pc.close() for pc in pcs]
		loop.run_until_complete(asyncio.gather(*coros))
