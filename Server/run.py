#!/usr/bin/env python3
import websockets
import asyncio
import sys
from server import Server

LISTEN_ADDRESS = ("0.0.0.0", 25568)  # 0.0.0.0 represents open to all, don't change. second number is port.

server = Server()
start_server = websockets.serve(server.client_handler, *LISTEN_ADDRESS)

loop = asyncio.get_event_loop()
loop.run_until_complete(start_server)
try:
	loop.run_forever()
except KeyboardInterrupt:
	print("Closing server")
	sys.exit()
