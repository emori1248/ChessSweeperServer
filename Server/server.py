import asyncio
import websockets
import json
import traceback

# The set of clients connected to this server. It is used to distribute
# messages.


class GameState():
	def __init__(self):
		self.fen = ''
		self.whitePlayer = None
		self.blackPlayer = None


class Api():
	def __init__(self, server, gameState):
		self.server = server
		self.gameState = gameState

	async def echoAll(self, args):
		for client in self.server.clients.keys():
			await self.server.send(client, args)


class Server():
	def __init__(self):
		self.clients = []
		self.gameState = GameState()
		self.api = Api(self, self.gameState)

	async def client_handler(self, websocket, path):
		print('New client', websocket)
		self.clients.append(websocket)
		print(f' ({len(self.clients)} existing clients)')

		# Handle messages from this client
		try:
			while True:
				message = await self.receive(websocket)

				if message is None:
					self.clients.remove(websocket)
					print('Client closed connection', websocket)
				elif "action" in message:
					response = {}
					try:
						if "args" in message:
							await Api.__dict__[message["action"]](self.api, message["args"])
						else:
							await Api.__dict__[message["action"]](self.api)
					except TypeError:
						traceback.print_exc()
						response = {
							"error": "Bad shape of command."
						}
					except KeyError:
						traceback.print_exc()
						response = {
							"error": "Invalid command."
						}
					if response:
						await self.send(websocket, response)
				else:
					# Only supports action format
					await self.send(websocket, {"error": "Invalid packet format"})

		except websockets.exceptions.ConnectionClosedOK:
			self.clients.remove(websocket)
			print('Client closed connection', websocket)

	async def send(self, websocket, message):
		await websocket.send(json.dumps(message))

	async def receive(self, websocket):
		return json.loads(await websocket.recv())
