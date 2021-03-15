# WebRTC 实时视频监控搭建

## 服务器搭建
服务器使用 janus 开源框架。
### 下载和编译Janus
#### 1.依赖安装
```shell script
sudo aptitude install libmicrohttpd-dev libjansson-dev libnice-dev \
    libssl1.0.1-dev libsrtp-dev libsofia-sip-ua-dev libglib2.3.4-dev \
    libopus-dev libogg-dev libcurl4-openssl-dev pkg-config gengetopt \
    libtool automake

sudo apt install cmake
sudo aptitude install libconfig-dev
sudo aptitude install libssl-dev
sudo aptitude install doxygen graphviz

# ffmpeg库 支持--enable-post-processing
sudo aptitude install libavcodec-dev libavformat-dev libswscale-dev libavutil-dev
```
#### 2.安装WebSocket
```shell script
git clone https://github.com/warmcat/libwebsockets.git
cd libwebsockets
git branch -a 查看选择最新的稳定版本，目前的是remotes/origin/v3.2-stable
git checkout v3.2-stable 切换到最新稳定版本
mkdir build
cd build
cmake -DCMAKE_INSTALL_PREFIX:PATH=/usr -DCMAKE_C_FLAGS="-fpic" ..
make && sudo make install
```
#### 3.安装libsrtp
```shell script
wget https://github.com/cisco/libsrtp/archive/v2.2.0.tar.gz
tar xfv v2.2.0.tar.gz
cd libsrtp-2.2.0
./configure --prefix=/usr --enable-openssl
make shared_library && sudo make install
```
#### 4.安装libusrsctp
```shell script
git clone https://github.com/Kurento/libusrsctp.git
cd libusrsctp
./bootstrap
./configure
make
sudo make install
```
#### 5.安装libmicrohttpd
```shell script
wget https://ftp.gnu.org/gnu/libmicrohttpd/libmicrohttpd-0.9.71.tar.gz
tar zxf libmicrohttpd-0.9.71.tar.gz
cd libmicrohttpd-0.9.71/
./configure
make
sudo make install
```
### 编译janus
#### 1.下载源码
```shell script
git clone https://github.com/meetecho/janus-gateway.git
git tag 查看当前的 tag,选择最新稳定的版本v0.10.4
git  checkout v0.10.4
sh autogen.sh
```
#### 2.编译
```shell script
./configure --prefix=/opt/janus --enable-websockets --enable-post-processing --enable-docs --enable-rest --enable-data-channels
make
sudo make install
```
### 配置和运行janus
#### 1.配置nginx
##### 生成证书:
```shell script
mkdir -p ~/cert
cd ~/cert
# CA私钥
openssl genrsa -out key.pem 2048
# 自签名证书
openssl req -new -x509 -key key.pem -out cert.pem -days 1095
```
##### 安装nginx:
```shell script
#下载nginx 1.15.8版本
wget http://nginx.org/download/nginx-1.15.8.tar.gz
tar xvzf nginx-1.15.8.tar.gz
cd nginx-1.15.8/


# 配置，一定要支持https
./configure --with-http_ssl_module 

# 编译
make

#安装
sudo make install 
```
##### 修改nginx配置文件:
/usr/local/nginx/conf/nginx.conf
```shell script
# HTTPS server
    #
    server {
        listen       443 ssl;
        server_name  localhost;
        # 配置相应的key
        ssl_certificate      /home/ubuntu/cert/cert.pem;
        ssl_certificate_key  /home/ubuntu/cert/key.pem;

        ssl_session_cache    shared:SSL:1m;
        ssl_session_timeout  5m;

        ssl_ciphers  HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers  on;
        # 指向janus demo所在目录
        location / {
            root   /opt/janus/share/janus/demos;
            index  videoroomdemo.html videoroomdemo.htm;
        }
    }
```
##### 启动nginx:
`sudo /usr/local/nginx/sbin/nginx`
#### 2.安装和启动coturn
##### 安装：
```shell script
sudo apt-get install libssl-dev
sudo apt-get install libevent-dev
wget http://coturn.net/turnserver/v4.5.0.7/turnserver-4.5.0.7.tar.gz
tar xfz turnserver-4.5.0.7.tar.gz
cd turnserver-4.5.0.7
 
./configure 
make 
sudo make install
```
##### 启动：
```shell script
sudo nohup turnserver -L 0.0.0.0 --min-port 30000 --max-port 60000  -a -u lqf:123456 -v -f -r nort.gov &
```
#### 3.配置janus的jcfg文件
要先把.sample后缀的文件拷贝成jcfg后缀
```shell script
# 进到对应的目录
cd /opt/janus/etc/janus
# 拷贝文件
sudo cp janus.jcfg.sample janus.jcfg
sudo cp janus.transport.http.jcfg.sample janus.transport.http.jcfg
sudo cp janus.transport.websockets.jcfg.sample janus.transport.websockets.jcfg
sudo cp janus.plugin.videoroom.jcfg.sample janus.plugin.videoroom.jcfg
sudo cp janus.transport.pfunix.jcfg.sample janus.transport.pfunix.jcfg
```
配置janus.jcfg
```shell script
# 大概237行
stun_server = "111.229.231.225"
        stun_port = 3478
        nice_debug = false

#大概274行
# credentials to authenticate...
        turn_server = "111.229.231.225"
        turn_port = 3478
        turn_type = "udp"
        turn_user = "lqf"
        turn_pwd = "123456"
```
配置janus.transport.http.jcfg
```shell script
general: {
        #events = true                                  # Whether to notify event handlers about transport events (default=true)
        json = "indented"                               # Whether the JSON messages should be indented (default),
                                                                        # plain (no indentation) or compact (no indentation and no spaces)
        base_path = "/janus"                    # Base path to bind to in the web server (plain HTTP only)
        threads = "unlimited"                   # unlimited=thread per connection, number=thread pool
        http = true                                             # Whether to enable the plain HTTP interface
        port = 8088                                             # Web server HTTP port
        #interface = "eth0"                             # Whether we should bind this server to a specific interface only
        #ip = "192.168.0.1"                             # Whether we should bind this server to a specific IP address (v4 or v6) only
        https = true                                    # Whether to enable HTTPS (default=false)
        secure_port = 8089                              # Web server HTTPS port, if enabled
        #secure_interface = "eth0"              # Whether we should bind this server to a specific interface only
        #secure_ip = "192.168.0.1"              # Whether we should bind this server to a specific IP address (v4 or v6) only
        #acl = "127.,192.168.0."                # Only allow requests coming from this comma separated list of addresses
}

certificates: {
        cert_pem = "/home/ubuntu/cert/cert.pem"
        cert_key = "/home/ubuntu/cert/key.pem"
        #cert_pwd = "secretpassphrase"
        #ciphers = "PFS:-VERS-TLS1.0:-VERS-TLS1.1:-3DES-CBC:-ARCFOUR-128"
}

```
配置janus.transport.websockets.jcfg
```shell script
general: {
        #events = true                                  # Whether to notify event handlers about transport events (default=true)
        json = "indented"                               # Whether the JSON messages should be indented (default),
                                                                        # plain (no indentation) or compact (no indentation and no spaces)
        #pingpong_trigger = 30                  # After how many seconds of idle, a PING should be sent
        #pingpong_timeout = 10                  # After how many seconds of not getting a PONG, a timeout should be detected

        ws = true                                               # Whether to enable the WebSockets API
        ws_port = 8188                                  # WebSockets server port
        #ws_interface = "eth0"                  # Whether we should bind this server to a specific interface only
        #ws_ip = "192.168.0.1"                  # Whether we should bind this server to a specific IP address only
        wss = true                                              # Whether to enable secure WebSockets
        wss_port = 8989                         # WebSockets server secure port, if enabled
        #wss_interface = "eth0"                 # Whether we should bind this server to a specific interface only
        #wss_ip = "192.168.0.1"                 # Whether we should bind this server to a specific IP address only
        #ws_logging = "err,warn"                # libwebsockets debugging level as a comma separated list of things
                                                                        # to debug, supported values: err, warn, notice, info, debug, parser,
                                                                        # header, ext, client, latency, user, count (plus 'none' and 'all')
        #ws_acl = "127.,192.168.0."             # Only allow requests coming from this comma separated list of addresses
}

certificates: {
        cert_pem = "/home/ubuntu/cert/cert.pem"
        cert_key = "/home/ubuntu/cert/key.pem"
        #cert_pwd = "secretpassphrase"
}
```
#### 4.运行Janus
`/opt/janus/bin/janus --debug-level=5 --log-file=$HOME/janus-log`
### 修改Videoroom源码
####1. 禁用videoroom摄像头
将videoroomtest.js 403行:
```javascript
media: { audioRecv: false, videoRecv: true, audioSend: useAudio, videoSend: true }
```
改为
```javascript
media: { audioRecv: false, videoRecv: false, audioSend: useAudio, videoSend: true }
```
