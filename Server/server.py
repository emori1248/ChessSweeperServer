import asyncio
import websockets
import json
import traceback
import random
import chess


class GameState():
	def __init__(self):
		self.game = chess.Board()
		self.mineLocs = []
		self.prevMove = {}
		self.whitePlayer = None
		self.blackPlayer = None

		self.genMSBoard()

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

	def genMSBoard(self):
		mineCount = 12
		squareCount = 64
		self.mineLocs = []
		while len(self.mineLocs) < mineCount / 2:
			loc = random.randint(0, squareCount/2 - 1)
			if not loc in self.mineLocs:
				self.mineLocs.append(loc)
		while len(self.mineLocs) < mineCount:
			loc = random.randint(squareCount / 2, squareCount - 1)
			if not loc in self.mineLocs:
				self.mineLocs.append(loc)


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

	async def claimWhite(self, client):
		error = self.gameState.setColor(client, "w")
		if error:
			return {
				"error": error
			}

		await self.server.sendAll({
			"action": "whiteClaimed",
			"args": {
				"taken": True
			}
		}, exclude=[client])

		if self.gameState.whitePlayer and self.gameState.blackPlayer:
			await self.server.sendAll({"action": "startGame"})

		return {
			"success": True
		}

	async def claimBlack(self, client):
		error = self.gameState.setColor(client, "b")
		if error:
			return {
				"error": error
			}

		await self.server.sendAll({
			"action": "blackClaimed",
			"args": {
				"taken": True
			}
		}, exclude=[client])

		if self.gameState.whitePlayer and self.gameState.blackPlayer:
			await self.server.sendAll({"action": "startGame"})

		return {
			"success": True
		}

	async def resetBoard(self, client):
		self.gameState.__init__()
		await self.server.sendAll({
			"action": "resetBoard",
			"args": {
				"fen": self.gameState.game.fen(),
				"mineCount": len(self.gameState.mineLocs),
				"prevMove": self.gameState.prevMove,
				"whitePlayer": bool(self.gameState.whitePlayer),
				"blackPlayer": bool(self.gameState.blackPlayer)
			}
		})

	async def move(self, client, args):
		if "skip" in args and args["skip"]:
			self.gameState.game.push(chess.Move.null())
			await self.server.sendAll({"action": "moveAll"}, exclude=[client])
		else:
			self.gameState.game.push(chess.Move.from_uci(f'{args["move"]["from"]}{args["move"]["to"]}{args["move"]["promotion"] if "promotion" in args["move"] else ""}'))
			self.gameState.prevMove = args["move"]

			await self.server.sendAll({
				"action": "moveAll",
				"args": args["move"]
			}, exclude=[client])

		return {
			"success": True
		}

	async def resetMS(self, client):
		self.gameState.genMSBoard()

	async def sink(self, client, args):
		print(args)
		return {
			"success": True,
			"squares": [{
				"position": args["square"]
			}]
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
		await self.send(client, {
			"action": "setFen",
			"args": {
				"fen": self.gameState.game.fen(),
				"mineCount": len(self.gameState.mineLocs),
				"prevMove": self.gameState.prevMove,
				"whitePlayer": bool(self.gameState.whitePlayer),
				"blackPlayer": bool(self.gameState.blackPlayer)
			}
		})

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
			if client == self.gameState.whitePlayer:
				self.gameState.whitePlayer = None
				await self.sendAll({
					"action": "whiteClaimed",
					"args": {
						"taken": False
					}
				})
			if client == self.gameState.blackPlayer:
				self.gameState.blackPlayer = None
				await self.sendAll({
					"action": "blackClaimed",
					"args": {
						"taken": False
					}
				})
			print('Client closed connection', client)

	async def send(self, client, message):
		await client.send(json.dumps(message))

	async def sendAll(self, message, exclude=[]):
		for c in self.clients:
			if not c in exclude:
				await self.send(c, message)

	async def receive(self, client):
		return json.loads(await client.recv())
