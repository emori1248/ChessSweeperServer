import asyncio
import websockets
import json
import traceback


class GameState():
	def __init__(self):
		self.fen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
		self.whitePlayer = None
		self.blackPlayer = None

	def setColor(self, client, color):
		if color == "w":
			if self.whitePlayer is None:
				self.whitePlayer = client
			else:
				return "White is already being played by another player."
		elif color == "b":
			if self.blackPlayer is None:
				self.blackPlayer = client
			else:
				return "Black is already being played by another player."
		else:
			return "Invalid color."


class Api():
	def __init__(self, server, gameState):
		self.server = server
		self.gameState = gameState

	async def echoAll(self, client, args):
		for c in self.server.clients:
			await self.server.send(c, {
				"action": "echoAll",
				"args": args
			})

	async def claimColor(self, client, args):
		if "color" in args:
			error = self.gameState(client, args["color"])
			if error:
				return {
					"error": error
				}
		else:
			return {
				"error": "Invalid arguments"
			}

		if self.gameState.whitePlayer and self.gameState.blackPlayer:
			await self.server.sendAll({"action": "startGame"})

		return {
			"success": True
		}


class Server():
	def __init__(self):
		self.clients = []
		self.gameState = GameState()
		self.api = Api(self, self.gameState)

	async def client_handler(self, client, path):
		print('New client', client)
		self.clients.append(client)
		print(f' ({len(self.clients)} existing clients)')

		# Handle messages from this client
		try:
			while True:
				message = await self.receive(client)

				if message is None:
					self.clients.remove(client)
					print('Client closed connection', client)
				elif "action" in message:
					response = {}
					try:
						if "args" in message:
							response = await Api.__dict__[message["action"]](self.api, client, message["args"])
						else:
							response = await Api.__dict__[message["action"]](self.api, client)

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
						await self.send(client, {
							"action": message["action"],
							"args": response
						})
				else:
					# Only supports action format
					await self.send(client, {"error": "Invalid packet format"})

		except websockets.exceptions.ConnectionClosedOK:
			self.clients.remove(client)
			print('Client closed connection', client)

	async def send(self, websocket, message):
		await websocket.send(json.dumps(message))

	async def sendAll(self, message):
		for c in self.clients:
			await self.send(c, message)

	async def receive(self, websocket):
		return json.loads(await websocket.recv())
