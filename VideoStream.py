class VideoStream:
	def __init__(self, filename):
		self.filename = filename
		try:
			self.file = open(filename, 'rb')
		except:
			raise IOError
		self.frameNum = 0
		
	def nextFrame(self):
		"""Get next frame."""
		data = self.file.read(5) # Get the framelength from the first 5 bits
		if not data:
			return None
			
		try:
			framelength = int(data)
		except ValueError:
			# Bẫy lỗi: Khung hình quá lớn hoặc video hỏng cấu trúc
			print(f"[!] Frame {self.frameNum + 1} corrupted. Stopping stream safely.")
			return None
							
		# Read the current frame
		frame_data = self.file.read(framelength)
		self.frameNum += 1
		return frame_data
		
	def frameNbr(self):
		"""Get frame number."""
		return self.frameNum