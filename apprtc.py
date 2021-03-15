from aiortc.contrib.signaling import ApprtcSignaling, BYE
import random
from aiortc import (
	RTCIceCandidate,
	RTCPeerConnection,
	RTCSessionDescription,
	VideoStreamTrack,
	RTCConfiguration,
	RTCIceServer,
)
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder
import asyncio
import cv2
from av import VideoFrame


class VideoCameraTrack(VideoStreamTrack):
	def __init__(self):
		super().__init__()
		self.cap = cv2.VideoCapture(0)

	async def recv(self):
		pts, time_base = await self.next_timestamp()
		_, img = self.cap.read()
		frame = VideoFrame.from_ndarray(img, format="bgr24")
		frame.pts = pts
		frame.time_base = time_base
		return frame


async def run(pc, recorder, signaling):
	def add_tracks():
		pc.addTrack(VideoCameraTrack())

	@pc.on("track")
	def on_track(track):
		recorder.addTrack(track)

	params = await signaling.connect()

	if params["is_initiator"] == "true":
		# send offer
		add_tracks()
		await pc.setLocalDescription(await pc.createOffer())
		await signaling.send(pc.localDescription)

	# consume signaling
	while True:
		obj = await signaling.receive()

		if isinstance(obj, RTCSessionDescription):
			await pc.setRemoteDescription(obj)
			await recorder.start()

			if obj.type == "offer":
				# send answer
				add_tracks()
				await pc.setLocalDescription(await pc.createAnswer())
				await signaling.send(pc.localDescription)
		elif isinstance(obj, RTCIceCandidate):
			await pc.addIceCandidate(obj)
		elif obj is BYE:
			print("Exiting")
			break


if __name__ == "__main__":
	room = "".join([random.choice("0123456789") for x in range(10)])
	# room = input("输入房间号:")
	urls = "https://wangxin1210.xyz"
	signaling = ApprtcSignaling(room)
	signaling._origin = urls

	config = RTCConfiguration([
		RTCIceServer("turn:42.194.190.40:3478", username='wx', credential='926492', credentialType='password')
	])
	pc = RTCPeerConnection(configuration=config)
	recorder = MediaBlackhole()
	loop = asyncio.get_event_loop()
	try:
		loop.run_until_complete(
			run(pc, recorder, signaling)
		)
	except KeyboardInterrupt:
		pass
	finally:
		loop.run_until_complete(recorder.stop())
		loop.run_until_complete(signaling.close())
		loop.run_until_complete(pc.close())
