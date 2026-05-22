import sys, socket, select
from ServerWorker import ServerWorker

class Server:	
	def main(self):
		try:
			SERVER_PORT = int(sys.argv[1])
		except:
			print("[Usage: python3 Server.py Server_port]\n")
			sys.exit()

		# Khởi tạo Socket Server (TCP)
		rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		# Cho phép dùng lại port ngay lập tức nếu Server vừa bị tắt/crash
		rtspSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		rtspSocket.bind(('', SERVER_PORT))
		rtspSocket.listen(5)        

		# Danh sách các socket mà hệ thống cần lắng nghe
		inputs = [rtspSocket]
		
		# Từ điển (Dictionary) để quản lý: { Client_Socket : Đối_tượng_ServerWorker }
		workers = {} 

		print(f"[*] Server is listening on port {SERVER_PORT} using I/O Multiplexing...")

		# BẮT ĐẦU KHỐI LỆNH BẢO VỆ CHỐNG LỖI CTRL+C
		try:
			while inputs:
				# Hàm select sẽ block ở đây, chờ cho đến khi có ít nhất 1 socket có dữ liệu
				readable, writable, exceptional = select.select(inputs, [], inputs)

				for s in readable:
					if s is rtspSocket:
						# 1. Có một Client MỚI yêu cầu kết nối
						connSocket, clientAddr = s.accept()
						print(f"\n[+] New connection accepted from {clientAddr}")
						
						# Chuyển socket của client thành non-blocking
						connSocket.setblocking(0)
						inputs.append(connSocket)

						# Khởi tạo Worker quản lý Client này
						clientInfo = {'rtspSocket': (connSocket, clientAddr)}
						workers[connSocket] = ServerWorker(clientInfo)
					
					else:
						# 2. Có dữ liệu (Lệnh RTSP) gửi đến từ một Client CŨ
						try:
							data = s.recv(1024)
							if data:
								print(f"Data received from {s.getpeername()}:\n{data.decode('utf-8')}")
								# Chuyển dữ liệu cho Worker tương ứng xử lý ngay lập tức
								workers[s].processRtspRequest(data.decode("utf-8"))
							else:
								# Nếu recv trả về data rỗng -> Client đã chủ động ngắt kết nối
								print(f"[-] Client {s.getpeername()} disconnected.")
								if s in inputs:
									inputs.remove(s)
								s.close()
								del workers[s]
						except Exception as e:
							print(f"[!] Error handling client: {e}")
							if s in inputs:
								inputs.remove(s)
							s.close()
							if s in workers:
								del workers[s]

				# Xử lý các socket bị lỗi ngoại lệ hệ thống
				for s in exceptional:
					print("[!] Exceptional condition on socket")
					inputs.remove(s)
					s.close()
					del workers[s]

		except KeyboardInterrupt:
			# Khối lệnh này chạy khi bạn nhấn Ctrl + C ở Terminal
			print("\n[!] Admin requested shutdown (Ctrl+C).")
			
		finally:
			# Dù chương trình tắt đúng cách hay bị lỗi đột xuất, khối này luôn chạy để giải phóng tài nguyên
			print("[*] Closing all active sockets and cleaning up system resources...")
			for s in inputs:
				try:
					s.close()
				except:
					pass
			print("[*] Server completely offline. Safe to restart!")

if __name__ == "__main__":
	(Server()).main()