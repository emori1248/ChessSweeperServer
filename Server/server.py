import asyncio
import websockets
import json
import traceback
import random
import chess
import math


class GameState():
	def __init__(self):
		self.game = chess.Board()
		self.mineLocs = []
		self.prevMove = {}
		self.whitePlayer = None
		self.blackPlayer = None
		self.timeControls = [300, 5]
		self.whiteTimer = self.timeControls[0]
		self.blackTimer = self.timeControls[0]
		self.whiteFreeSink = True
		self.blackFreeSink = True

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

	def getSinkSquares(self, squares, findAdj={}):
		if not findAdj:  #this argument is only meant to be used in recursive calls
			findAdj = squares.copy()

		for k in tuple(findAdj):
			index = chess.parse_square(k)
			mineCount = 0
			adj = []
			for i in [-9, -7, 7, 9]:  #corners
				if index + i >= 0 and index + i < 64 and abs(math.floor((index+i) / 8) - math.floor(index / 8)) == 1 and abs((index+i) % 8 - index%8) == 1:  #row and column distance is 1
					if index + i in self.mineLocs:
						mineCount += 1
					adj.append(index + i)
			for i in [-8, 8]:  #above and below
				if index + i >= 0 and index + i < 64 and abs(math.floor((index+i) / 8) - math.floor(index / 8)) == 1 and abs((index+i) % 8 - index%8) == 0:  #row distance is 1, column distance is 0
					if index + i in self.mineLocs:
						mineCount += 1
					adj.append(index + i)
			for i in [-1, 1]:  #left and right
				if index + i >= 0 and index + i < 64 and abs(math.floor((index+i) / 8) - math.floor(index / 8)) == 0 and abs((index+i) % 8 - index%8) == 1:  #row distance is 0, column distance is 1
					if index + i in self.mineLocs:
						mineCount += 1
					adj.append(index + i)

			squares[k] = mineCount
			if mineCount == 0:
				adjDict = {chess.square_name(key): val
							for key, val in dict.fromkeys(adj).items()}
				for i in adj:  #simple solution
					j = chess.square_name(i)
					if j in squares.keys():
						del adjDict[j]
				if adjDict:
					self.getSinkSquares(squares, adjDict)


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
		if client == self.gameState.whitePlayer or client == self.gameState.blackPlayer:
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
		else:
			return {
				"error": "Only registered players can reset the game."
			}

	async def move(self, client, args):
		if self.gameState.game.turn == chess.WHITE:
			self.gameState.whiteTimer = args["timer"]
		else:
			self.gameState.blackTimer = args["timer"]

		extraInfo = {}
		if "skip" in args and args["skip"]:
			self.gameState.game.push(chess.Move.null())
			self.gameState.prevMove = {}

			extraInfo["turnCount"] = self.gameState.game.fullmove_number
			if (self.gameState.game.ply()) % 20 == 0:
				self.gameState.genMSBoard()
				extraInfo["resetMS"] = True
				self.gameState.whiteFreeSink = True
				self.gameState.blackFreeSink = True

			await self.server.sendAll({
				"action": "moveAll",
				"args": {
					"timers": {
						"whiteTimer": self.gameState.whiteTimer,
						"blackTimer": self.gameState.blackTimer
					},
					"extraInfo": extraInfo
				}
			})
		else:
			self.gameState.game.push(chess.Move.from_uci(f'{args["move"]["from"]}{args["move"]["to"]}{args["move"]["promotion"] if "promotion" in args["move"] else ""}'))
			self.gameState.prevMove = args["move"]

			rank = "8" if args["move"]["color"] == "b" else "1"
			if "k" in args["move"]["flags"]:  #kingside castle
				square = chess.parse_square(f"f{rank}")
				if square in self.gameState.mineLocs:
					self.gameState.game.remove_piece_at(square)
					extraInfo["kcMine"] = True
			if "q" in args["move"]["flags"]:  #queenside castle
				square = chess.parse_square(f"d{rank}")
				if square in self.gameState.mineLocs:
					self.gameState.game.remove_piece_at(square)
					extraInfo["qcMine"] = True

			if chess.parse_square(args["move"]["to"]) in self.gameState.mineLocs:
				self.gameState.game.remove_piece_at(chess.parse_square(args["move"]["to"]))
				extraInfo["mine"] = True

			extraInfo["turnCount"] = self.gameState.game.fullmove_number
			if (self.gameState.game.ply()) % 20 == 0:
				self.gameState.genMSBoard()
				extraInfo["resetMS"] = True
				self.gameState.whiteFreeSink = True
				self.gameState.blackFreeSink = True

			await self.server.sendAll({
				"action": "moveAll",
				"args": {
					"move": args["move"],
					"extraInfo": extraInfo,
					"timers": {
						"whiteTimer": self.gameState.whiteTimer,
						"blackTimer": self.gameState.blackTimer
					}
				}
			})

	# async def resetMS(self, client):
	# 	self.gameState.genMSBoard()

	async def sink(self, client, args):
		squares = {}
		reveal = True
		if chess.parse_square(args["position"]) in self.gameState.mineLocs:
			squares[args["position"]] = "mine"
			if not (client == self.gameState.whitePlayer and self.gameState.whiteFreeSink) and not (client == self.gameState.blackPlayer and self.gameState.blackFreeSink):
				await self.move(client, {
					"skip": True,
					"timer": args["timer"]
				})
				if (self.gameState.game.ply()) % 20 == 0:
					reveal = False
		else:
			squares[args["position"]] = None
			self.gameState.getSinkSquares(squares)

		if client == self.gameState.whitePlayer and self.gameState.whiteFreeSink:
			self.gameState.whiteFreeSink = False
		elif client == self.gameState.blackPlayer and self.gameState.blackFreeSink:
			self.gameState.blackFreeSink = False

		return {
			"success": True,
			"squares": squares,
			"reveal": reveal
		}

	async def getControls(self, client):
		return {
			"success": True,
			"timeControls": self.gameState.timeControls
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
			"action": "setBoard",
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
						if "__" in message["action"]:
							response = {
								"error": "Can't invoke built-in functions."
							}
						elif "args" in message:
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

		except (websockets.exceptions.ConnectionClosedOK, websockets.exceptions.ConnectionClosedError):
			self.clients.remove(client)
			if client == self.gameState.whitePlayer:
				self.gameState.whitePlayer = None
				self.gameState.__init__()
				await self.sendAll({
					"action": "whiteClaimed",
					"args": {
						"taken": False,
						"fen": self.gameState.game.fen(),
						"mineCount": len(self.gameState.mineLocs)
					}
				})
			if client == self.gameState.blackPlayer:
				self.gameState.blackPlayer = None
				self.gameState.__init__()
				await self.sendAll({
					"action": "blackClaimed",
					"args": {
						"taken": False,
						"fen": self.gameState.game.fen(),
						"mineCount": len(self.gameState.mineLocs)
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
