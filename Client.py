import time
from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os

from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client:
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT
	
	SETUP = 0
	PLAY = 1
	PAUSE = 2
	TEARDOWN = 3
	
	# Initiation..
	def __init__(self, master, serveraddr, serverport, rtpport, filename):
		self.master = master
		self.master.protocol("WM_DELETE_WINDOW", self.handler)
		self.createWidgets()
		self.serverAddr = serveraddr
		self.serverPort = int(serverport)
		self.rtpPort = int(rtpport)
		self.fileName = filename
		self.rtspSeq = 0
		self.sessionId = 0
		self.requestSent = -1
		self.teardownAcked = 0
		self.connectToServer()
		self.frameNbr = 0
		
	def createWidgets(self):
		"""Build GUI."""
		# Create Setup button
		self.setup = Button(self.master, width=20, padx=3, pady=3)
		self.setup["text"] = "Setup"
		self.setup["command"] = self.setupMovie
		self.setup.grid(row=1, column=0, padx=2, pady=2)
		
		# Create Play button		
		self.start = Button(self.master, width=20, padx=3, pady=3)
		self.start["text"] = "Play"
		self.start["command"] = self.playMovie
		self.start.grid(row=1, column=1, padx=2, pady=2)
		
		# Create Pause button			
		self.pause = Button(self.master, width=20, padx=3, pady=3)
		self.pause["text"] = "Pause"
		self.pause["command"] = self.pauseMovie
		self.pause.grid(row=1, column=2, padx=2, pady=2)
		
		# Create Teardown button
		self.teardown = Button(self.master, width=20, padx=3, pady=3)
		self.teardown["text"] = "Teardown"
		self.teardown["command"] =  self.exitClient
		self.teardown.grid(row=1, column=3, padx=2, pady=2)
		
		# Create a label to display the movie
		self.label = Label(self.master, height=19)
		self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 
		# Thêm giao diện chọn độ phân giải / giao thức mạng
		self.resolution = StringVar()
		self.resolution.set("SD") # Mặc định chọn SD
		
		self.sd_btn = Radiobutton(self.master, text="SD-540 (UDP)", variable=self.resolution, value="SD", command=self.changeResolution)
		self.sd_btn.grid(row=2, column=0, padx=2, pady=2)
		
		self.hd720_btn = Radiobutton(self.master, text="HD-720 (TCP)", variable=self.resolution, value="HD720", command=self.changeResolution)
		self.hd720_btn.grid(row=2, column=1, padx=2, pady=2)
		
		self.hd1080_btn = Radiobutton(self.master, text="HD-1080 (TCP)", variable=self.resolution, value="HD1080", command=self.changeResolution)
		self.hd1080_btn.grid(row=2, column=2, padx=2, pady=2)
		
		# Khởi tạo biến lưu cấu hình giao thức truyền dữ liệu media
		self.streamType = "UDP"

		# Thanh trạng thái Telemetry & Monitoring
		self.statLabel = Label(self.master, text="Metrics: Waiting for stream...", font=("Helvetica", 12, "italic"))
		self.statLabel.grid(row=3, column=0, columnspan=4, pady=5)

	def changeResolution(self):
		if self.resolution.get() == "SD":
			self.streamType = "UDP"
		else:
			self.streamType = "TCP"
		print(f"[*] Switched streaming protocol to {self.streamType}")
	
	def setupMovie(self):
		"""Setup button handler."""
		if self.state == self.INIT:
			self.sendRtspRequest(self.SETUP)
	
	def exitClient(self):
		"""Teardown button handler."""
		self.sendRtspRequest(self.TEARDOWN)		
		self.master.destroy() # Close the gui window
		
		# Bọc try-except để không bị văng lỗi nếu chưa có file video
		try:
			os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)
		except OSError:
			pass


	def pauseMovie(self):
		"""Pause button handler."""
		if self.state == self.PLAYING:
			self.sendRtspRequest(self.PAUSE)
	
	def playMovie(self):
		"""Play button handler."""
		if self.state == self.READY:
			self.playEvent = threading.Event()
			self.playEvent.clear()
			# -- BẮT ĐẦU ĐOẠN KHỞI TẠO METRICS --
			self.statStartTime = time.time()  
			self.statTotalBytes = 0           
			self.statTotalPackets = 0         
			self.statFirstSeq = -1            
			self.statLastSeq = 0              
			
			# THÊM 2 BIẾN NÀY CHO TỐC ĐỘ TỨC THỜI
			self.statWindowStartTime = time.time()
			self.statWindowBytes = 0
			# -- KẾT THÚC ĐOẠN KHỞI TẠO --

			threading.Thread(target=self.listenRtp).start()
			self.sendRtspRequest(self.PLAY)
	

	def listenRtp(self):		
		"""Listen for RTP packets and handle fragmentation or TCP byte-stream."""
		if self.streamType == "TCP":
			try:
				# Chấp nhận kết nối kênh truyền dữ liệu từ Server gửi tới
				self.rtpSocket, _ = self.rtpListenSocket.accept()
				self.rtpSocket.settimeout(0.5)
			except socket.timeout:
				print("[!] TCP Data connection timeout.")
				return
		receivedBuffer = bytearray()
		self.currentAssemblyFrame = -1

		# Mảng lưu trữ tích lũy dữ liệu khi bị phân mảnh gói tin
		receivedBuffer = bytearray()

		while True:
			try:
				if self.streamType == "TCP":

					len_bytes = self.rtpSocket.recv(4)
					if not len_bytes or len(len_bytes) < 4:
						break
					packet_len = int.from_bytes(len_bytes, byteorder='big')
					
					data = bytearray()
					while len(data) < packet_len:
						packet = self.rtpSocket.recv(packet_len - len(data))
						if not packet:
							break
						data.extend(packet)
						
					if data:
						rtpPacket = RtpPacket()
						rtpPacket.decode(data)
						currFrameNbr = rtpPacket.seqNum()
						
						# -- ĐO LƯỜNG METRICS --
						if getattr(self, 'statFirstSeq', -1) == -1:
							self.statFirstSeq = currFrameNbr
							self.statWindowStartTime = time.time()
							self.statWindowBytes = 0

						self.statLastSeq = currFrameNbr
						self.statTotalPackets += 1
						self.statWindowBytes = getattr(self, 'statWindowBytes', 0) + len(rtpPacket.getPayload())

						current_time = time.time()
						window_elapsed = current_time - getattr(self, 'statWindowStartTime', current_time)

						if window_elapsed >= 0.5:
							# 1. Tính tốc độ gốc theo byte/giây
							data_rate_bytes = self.statWindowBytes / window_elapsed
							
							# 2. Chuyển đổi sang MB/s (Chia cho 1024 * 1024)
							data_rate_mb = data_rate_bytes / (1024 * 1024)
							
							expected_packets = self.statLastSeq - self.statFirstSeq + 1
							loss_rate = max(0.0, 100 * (1 - (self.statTotalPackets / expected_packets))) if expected_packets > 0 else 0.0
							
							# 3. Cập nhật Text: Dùng {data_rate_mb:.2f} để lấy 2 chữ số thập phân
							stats_text = f"Protocol: {self.streamType} | Data Rate: {data_rate_mb:.2f} mb/s | Packet Loss: {loss_rate:.2f}%"
							
							self.master.after(0, lambda t=stats_text: self.statLabel.config(text=t))
							self.statWindowStartTime = current_time
							self.statWindowBytes = 0
						# -- KẾT THÚC METRICS --

						# HIỂN THỊ VIDEO TCP
						if currFrameNbr > self.frameNbr:
							self.frameNbr = currFrameNbr
							self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
							
				else:
					# LÀN UDP
					data = self.rtpSocket.recv(20480)
					if data:
						rtpPacket = RtpPacket()
						rtpPacket.decode(data)
						currFrameNbr = rtpPacket.seqNum()
						
						# -- ĐO LƯỜNG METRICS --
						if getattr(self, 'statFirstSeq', -1) == -1:
							self.statFirstSeq = currFrameNbr
							self.statWindowStartTime = time.time()
							self.statWindowBytes = 0

						self.statLastSeq = currFrameNbr
						self.statTotalPackets += 1
						self.statWindowBytes = getattr(self, 'statWindowBytes', 0) + len(rtpPacket.getPayload())

						current_time = time.time()
						window_elapsed = current_time - getattr(self, 'statWindowStartTime', current_time)

						if window_elapsed >= 0.5:
							# 1. Tính tốc độ gốc theo byte/giây
							data_rate_bytes = self.statWindowBytes / window_elapsed
							
							# 2. Chuyển đổi sang MB/s (Chia cho 1024 * 1024)
							data_rate_mb = data_rate_bytes / (1024 * 1024)
							
							expected_packets = self.statLastSeq - self.statFirstSeq + 1
							loss_rate = max(0.0, 100 * (1 - (self.statTotalPackets / expected_packets))) if expected_packets > 0 else 0.0
							
							# 3. Cập nhật Text: Dùng {data_rate_mb:.2f} để lấy 2 chữ số thập phân
							stats_text = f"Protocol: {self.streamType} | Data Rate: {data_rate_mb:.2f} mb/s | Packet Loss: {loss_rate:.2f}%"
							
							self.master.after(0, lambda t=stats_text: self.statLabel.config(text=t))
							self.statWindowStartTime = current_time
							self.statWindowBytes = 0
						# -- KẾT THÚC METRICS --

						# GOM MẢNH & HIỂN THỊ VIDEO UDP
						if currFrameNbr > getattr(self, 'currentAssemblyFrame', -1):
							self.currentAssemblyFrame = currFrameNbr
							receivedBuffer = bytearray()
						
						if currFrameNbr == getattr(self, 'currentAssemblyFrame', -1):
							receivedBuffer.extend(rtpPacket.getPayload())

		
						if rtpPacket.marker() == 1:
							if currFrameNbr > self.frameNbr:
								self.frameNbr = currFrameNbr
								try:
									self.updateMovie(self.writeFrame(bytes(receivedBuffer)))
								except Exception:
									pass
							receivedBuffer = bytearray()
			except:
				if self.playEvent.is_set(): 
					break
				if self.teardownAcked == 1:
					if self.streamType == "TCP":
						try:
							self.rtpListenSocket.close()
						except: pass
					self.rtpSocket.close()
					break
					
	def writeFrame(self, data):
		"""Write the received frame to a temp image file. Return the image file."""
		cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		file = open(cachename, "wb")
		file.write(data)
		file.close()
		
		return cachename
	
	def updateMovie(self, imageFile):
		"""Update the image file as video frame in the GUI."""
		photo = ImageTk.PhotoImage(Image.open(imageFile))
		self.label.configure(image = photo, height=288) 
		self.label.image = photo
		
	def connectToServer(self):
		"""Connect to the Server. Start a new RTSP/TCP session."""
		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			self.rtspSocket.connect((self.serverAddr, self.serverPort))
		except:
			tkinter.messagebox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)
	
	def sendRtspRequest(self, requestCode):
		"""Send RTSP request to the server."""	
		# Setup request
		if requestCode == self.SETUP and self.state == self.INIT:
			threading.Thread(target=self.recvRtspReply).start()
			self.rtspSeq += 1
			# Chú ý: Đã thêm một dấu cách sau 'client_port=' và dùng \n thay cho \r\n
			# Chèn biến động self.streamType vào chuỗi yêu cầu Transport
			request = f"SETUP {self.fileName} RTSP/1.0\n" \
					  f"CSeq: {self.rtspSeq}\n" \
					  f"Transport: RTP/{self.streamType}; client_port= {self.rtpPort}\n"
			self.requestSent = self.SETUP
		
		# Play request
		elif requestCode == self.PLAY and self.state == self.READY:
			self.rtspSeq += 1
			request = f"PLAY {self.fileName} RTSP/1.0\n" \
					  f"CSeq: {self.rtspSeq}\n" \
					  f"Session: {self.sessionId}\n"
			self.requestSent = self.PLAY
		
		# Pause request
		elif requestCode == self.PAUSE and self.state == self.PLAYING:
			self.rtspSeq += 1
			request = f"PAUSE {self.fileName} RTSP/1.0\n" \
					  f"CSeq: {self.rtspSeq}\n" \
					  f"Session: {self.sessionId}\n"
			self.requestSent = self.PAUSE
			
		# Teardown request
		elif requestCode == self.TEARDOWN and not self.state == self.INIT:
			self.rtspSeq += 1
			request = f"TEARDOWN {self.fileName} RTSP/1.0\n" \
					  f"CSeq: {self.rtspSeq}\n" \
					  f"Session: {self.sessionId}\n"
			self.requestSent = self.TEARDOWN
		else:
			return
		
		# Send the RTSP request using rtspSocket.
		self.rtspSocket.send(request.encode("utf-8"))
		
		print('\nData sent:\n' + request)
	
	def recvRtspReply(self):
		"""Receive RTSP reply from the server."""
		while True:
			try:
				reply = self.rtspSocket.recv(1024)
				
				if reply: 
					self.parseRtspReply(reply.decode("utf-8"))
				
				# Bọc riêng khối Teardown để chống lỗi Errno 57
				if self.teardownAcked == 1:
					self.rtpteardown = 1
					self.playEvent.set()
					try:
						self.rtspSocket.shutdown(socket.SHUT_RDWR)
					except OSError:
						# Bỏ qua nếu socket đã đóng hoặc lỗi
						pass
					finally:
						self.rtspSocket.close()
					break
			except Exception as e:
				# Bắt mọi lỗi xảy ra trong quá trình nhận dữ liệu
				print(f"[!] Lỗi kết nối RTSP hoặc Server đã ngắt: {e}")
				self.playEvent.set()
				try:
					self.rtspSocket.close()
				except:
					pass
				break
	
	def parseRtspReply(self, data):
		"""Parse the RTSP reply from the server."""
		lines = data.split('\n')
		seqNum = int(lines[1].split(' ')[1])
		
		# Process only if the server reply's sequence number is the same as the request's
		if seqNum == self.rtspSeq:
			session = int(lines[2].split(' ')[1])
			# New RTSP session ID
			if self.sessionId == 0:
				self.sessionId = session
			
			# Process only if the session ID is the same
			if self.sessionId == session:
				if int(lines[0].split(' ')[1]) == 200: 
					if self.requestSent == self.SETUP:
						#-------------
						# TO COMPLETE
						#-------------
						self.state = self.READY # Chuyển sang READY
						self.openRtpPort() 
					elif self.requestSent == self.PLAY:
						self.state = self.PLAYING # Chuyển sang PLAYING
					elif self.requestSent == self.PAUSE:
						self.state = self.READY # Quay lại READY
						self.playEvent.set()
					elif self.requestSent == self.TEARDOWN:
						self.state = self.INIT # Quay lại INIT
						self.teardownAcked = 1
	
	def openRtpPort(self):
		"""Open RTP socket binded to a specified port based on protocol type."""
		if self.streamType == "UDP":
			self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			# Nới rộng bộ đệm OS lên 1MB để chống rớt gói khi Server bắn nhanh
			self.rtpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
			self.rtpSocket.settimeout(0.5)
			try:
				self.rtpSocket.bind(('', self.rtpPort))
			except:
				tkinter.messagebox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)
		else:
			# Với chế độ TCP HD: Khởi tạo một socket Server để lắng nghe kết nối từ Server đổ về
			self.rtpListenSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.rtpListenSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			try:
				self.rtpListenSocket.bind(('', self.rtpPort))
				self.rtpListenSocket.listen(1)
				self.rtpListenSocket.settimeout(0.5)
			except:
				tkinter.messagebox.showwarning('Unable to Bind', 'Unable to bind TCP PORT=%d' %self.rtpPort)

	def handler(self):
		"""Handler on explicitly closing the GUI window."""
		self.pauseMovie()
		if tkinter.messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
			self.exitClient()
		else: # When the user presses cancel, resume playing.
			self.playMovie()
