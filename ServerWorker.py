import time
from random import randint
import sys, traceback, threading, socket

from VideoStream import VideoStream
from RtpPacket import RtpPacket

class ServerWorker:
	SETUP = 'SETUP'
	PLAY = 'PLAY'
	PAUSE = 'PAUSE'
	TEARDOWN = 'TEARDOWN'
	
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT

	OK_200 = 0
	FILE_NOT_FOUND_404 = 1
	CON_ERR_500 = 2
	
	clientInfo = {}
	
	def __init__(self, clientInfo):
		self.clientInfo = clientInfo
		
	# def run(self):
	# 	threading.Thread(target=self.recvRtspRequest).start()
	
	# def recvRtspRequest(self):
	# 	"""Receive RTSP request from the client."""
	# 	connSocket = self.clientInfo['rtspSocket'][0]
	# 	while True:            
	# 		data = connSocket.recv(256)
	# 		if data:
	# 			print("Data received:\n" + data.decode("utf-8"))
	# 			self.processRtspRequest(data.decode("utf-8"))
	
	def processRtspRequest(self, data):
		"""Process RTSP request sent from the client."""
		# Get the request type
		request = data.split('\n')
		line1 = request[0].split(' ')
		requestType = line1[0]
		
		# Get the media file name
		filename = line1[1]
		
		# Get the RTSP sequence number 
		seq = request[1].split(' ')
		
		# Process SETUP request (with a new logic)
		if requestType == self.SETUP:
			if self.state == self.INIT:
				print("processing SETUP\n")
				try:
					self.clientInfo['videoStream'] = VideoStream(filename)
					self.state = self.READY
				except IOError:
					self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
				
				self.clientInfo['session'] = randint(100000, 999999)
				self.replyRtsp(self.OK_200, seq[1])
				
				# Đọc Port mạng
				self.clientInfo['rtpPort'] = request[2].split(' ')[3]
				
				# KIỂM TRA XEM CLIENT MUỐN DÙNG TCP HAY UDP
				if "RTP/TCP" in request[2]:
					self.clientInfo['transport'] = 'TCP'
				else:
					self.clientInfo['transport'] = 'UDP'
		
		# Process PLAY request 		
		elif requestType == self.PLAY:
			if self.state == self.READY:
				print("processing PLAY\n")
				self.state = self.PLAYING
				
				# KHỞI TẠO SOCKET THEO GIAO THỨC ĐÃ CHỌN
				if self.clientInfo['transport'] == 'TCP':
					self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
					address = self.clientInfo['rtspSocket'][1][0]
					port = int(self.clientInfo['rtpPort'])
					# Server chủ động connect tới socket lắng nghe dữ liệu của Client
					self.clientInfo["rtpSocket"].connect((address, port))
				else:
					self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				
				self.replyRtsp(self.OK_200, seq[1])
				
				self.clientInfo['event'] = threading.Event()
				self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
				self.clientInfo['worker'].start()
		
		# Process PAUSE request
		elif requestType == self.PAUSE:
			if self.state == self.PLAYING:
				print("processing PAUSE\n")
				self.state = self.READY
				
				self.clientInfo['event'].set()
			
				self.replyRtsp(self.OK_200, seq[1])
		
		# Process TEARDOWN request
		elif requestType == self.TEARDOWN:
			print("processing TEARDOWN\n")

			self.clientInfo['event'].set()
			
			self.replyRtsp(self.OK_200, seq[1])
			
			# Close the RTP socket
			self.clientInfo['rtpSocket'].close()
			
	import time # Nhớ thêm dòng này ở đầu file nếu chưa có

# ... (bên trong class ServerWorker) ...

	def sendRtp(self):
		"""Send RTP packets with Fragmentation, Pacing, and EOF handling."""
		while True:
			self.clientInfo['event'].wait(0.05) 
			if self.clientInfo['event'].is_set(): 
				break 
				
			data = self.clientInfo['videoStream'].nextFrame()
			
			# NẾU NHẬN NONE -> ĐÃ HẾT VIDEO HOẶC FRAME LỖI
			if not data:
				print("[*] End of Video Stream reached. Stopping RTP transmission.")
				break # Phá vỡ vòng lặp, dừng gửi một cách êm ái
				
			frameNumber = self.clientInfo['videoStream'].frameNbr()
			try:
				if self.clientInfo['transport'] == 'TCP':
					# TCP không lo giới hạn kích thước, gửi cục lớn
					packet = self.makeRtp(data, frameNumber, marker=1)
					packet_len = len(packet)
					self.clientInfo['rtpSocket'].sendall(packet_len.to_bytes(4, byteorder='big') + packet)
				else:
					# UDP PHÂN MẢNH + ĐIỀU TỐC CHỐNG NGẬP LỤT
					address = self.clientInfo['rtspSocket'][1][0]
					port = int(self.clientInfo['rtpPort'])
					payload_size = 1400 # MTU an toàn
					
					if len(data) > payload_size:
						for i in range(0, len(data), payload_size):
							chunk = data[i:i+payload_size]
							marker = 1 if (i + payload_size >= len(data)) else 0
							packet = self.makeRtp(chunk, frameNumber, marker=marker)
							self.clientInfo['rtpSocket'].sendto(packet, (address, port))
							
							# Micro-delay: Ngủ 0.5 mili-giây để OS Client kịp hứng, chống nhiễu ảnh
							time.sleep(0.0005) 
					else:
						packet = self.makeRtp(data, frameNumber, marker=1)
						self.clientInfo['rtpSocket'].sendto(packet, (address, port))
			except Exception as e:
				# In ra lỗi thật sự thay vì đoán mù
				print(f"[!] Streaming aborted. Details: {e}")
				break

	def makeRtp(self, payload, frameNbr, marker=0):
		"""RTP-packetize the video data using dynamic marker."""
		version = 2
		padding = 0
		extension = 0
		cc = 0
		pt = 26 # MJPEG type
		seqnum = frameNbr
		ssrc = 0 
		
		rtpPacket = RtpPacket()
		# Sử dụng tham số biến marker truyền vào thay vì fix cứng bằng 0
		rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)
		return rtpPacket.getPacket()
		
	def replyRtsp(self, code, seq):
		"""Send RTSP reply to the client."""
		if code == self.OK_200:
			#print("200 OK")
			reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + str(self.clientInfo['session'])
			connSocket = self.clientInfo['rtspSocket'][0]
			connSocket.send(reply.encode())
		
		# Error messages
		elif code == self.FILE_NOT_FOUND_404:
			print("404 NOT FOUND")
		elif code == self.CON_ERR_500:
			print("500 CONNECTION ERROR")
