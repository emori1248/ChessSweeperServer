import websockets
import json
import traceback
import random
import chess
import math
import string


class GameState():
	def __init__(self):
		self.timeControls = [300, 5]
		self.mineCount = 12
		self.movesUntilReset = 10

		self.game = chess.Board()
		self.mineLocs = []
		self.prevMove = {}
		self.whitePlayer = None
		self.blackPlayer = None
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
		squareCount = 64
		self.mineLocs = []
		while len(self.mineLocs) < self.mineCount / 2:
			loc = random.randint(0, squareCount/2 - 1)
			if not loc in self.mineLocs:
				self.mineLocs.append(loc)
		while len(self.mineLocs) < self.mineCount:
			loc = random.randint(squareCount / 2, squareCount - 1)
			if not loc in self.mineLocs:
				self.mineLocs.append(loc)

	def getSinkSquares(self, squares, findAdj={}):
		if not findAdj:  #this argument is only meant to be used in recursive calls
			findAdj = squares.copy()

		for k in tuple(findAdj):
			index = chess.parse_square(k)
			minesFound = 0
			adj = []
			for i in [-9, -7, 7, 9]:  #corners
				if index + i >= 0 and index + i < 64 and abs(math.floor((index+i) / 8) - math.floor(index / 8)) == 1 and abs((index+i) % 8 - index%8) == 1:  #row and column distance is 1
					if index + i in self.mineLocs:
						minesFound += 1
					adj.append(index + i)
			for i in [-8, 8]:  #above and below
				if index + i >= 0 and index + i < 64 and abs(math.floor((index+i) / 8) - math.floor(index / 8)) == 1 and abs((index+i) % 8 - index%8) == 0:  #row distance is 1, column distance is 0
					if index + i in self.mineLocs:
						minesFound += 1
					adj.append(index + i)
			for i in [-1, 1]:  #left and right
				if index + i >= 0 and index + i < 64 and abs(math.floor((index+i) / 8) - math.floor(index / 8)) == 0 and abs((index+i) % 8 - index%8) == 1:  #row distance is 0, column distance is 1
					if index + i in self.mineLocs:
						minesFound += 1
					adj.append(index + i)

			squares[k] = minesFound
			if minesFound == 0:
				adjDict = {chess.square_name(key): val
							for key, val in dict.fromkeys(adj).items()}
				for i in adj:  #simple solution
					j = chess.square_name(i)
					if j in squares.keys():
						del adjDict[j]
				if adjDict:
					self.getSinkSquares(squares, adjDict)

	def reset(self, removePlayers=True):
		self.game = chess.Board()
		self.mineLocs = []
		self.prevMove = {}
		if removePlayers:
			self.whitePlayer = None
			self.blackPlayer = None
		self.whiteTimer = self.timeControls[0]
		self.blackTimer = self.timeControls[0]
		self.whiteFreeSink = True
		self.blackFreeSink = True

		self.genMSBoard()


class Lobby():
	def __init__(self, server, lobbyClients):
		self.gameState = GameState()
		self.server = server
		self.lobbyClients = lobbyClients

	# async def echoAll(self, client, args):
	# 	for c in self.server.clients:
	# 		await self.server.send(c, {
	# 			"action": "echoAll",
	# 			"args": args
	# 		})

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
		}, self.lobbyClients, exclude=[client])

		if self.gameState.whitePlayer and self.gameState.blackPlayer:
			await self.server.sendAll({"action": "startGame"}, self.lobbyClients)

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
		}, self.lobbyClients, exclude=[client])

		if self.gameState.whitePlayer and self.gameState.blackPlayer:
			await self.server.sendAll({"action": "startGame"}, self.lobbyClients)

		return {
			"success": True
		}

	async def resetBoard(self, client, removePlayers=True):
		if client == self.gameState.whitePlayer or client == self.gameState.blackPlayer:
			self.gameState.reset(removePlayers)
			await self.server.sendAll({
				"action": "resetBoard",
				"args": {
					"fen": self.gameState.game.fen(),
					"mineCount": len(self.gameState.mineLocs),
					"prevMove": self.gameState.prevMove,
					"timeControls": self.gameState.timeControls,
					"whitePlayer": bool(self.gameState.whitePlayer),
					"blackPlayer": bool(self.gameState.blackPlayer)
				}
			}, self.lobbyClients)
		else:
			return {
				"error": "Only black or white can reset the game."
			}

	async def move(self, client, args):
		self.gameState.whiteTimer = args["timers"]["whiteTimer"]
		self.gameState.blackTimer = args["timers"]["blackTimer"]

		extraInfo = {}
		if "skip" in args and args["skip"]:
			self.gameState.game.push(chess.Move.null())
			self.gameState.prevMove = {}

			extraInfo["turnCount"] = self.gameState.game.fullmove_number
			if (self.gameState.game.ply()) % (self.gameState.movesUntilReset * 2) == 0:
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
			}, self.lobbyClients)
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
			}, self.lobbyClients)

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
					"timers": args["timers"]
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

	async def updateSettings(self, client, args):
		if not (client == self.gameState.whitePlayer or client == self.gameState.blackPlayer):
			return {
				"error": "Only black or white can update the game settings."
			}
		if args["startingTime"]:
			if not (args["startingTime"].isdigit() and int(args["startingTime"]) > 0):
				return {
					"error": "Starting time must be a positive integer."
				}
			self.gameState.timeControls[0] = int(args["startingTime"])
		if args["increment"]:
			if not (args["increment"].isdigit() and int(args["increment"]) >= 0):
				return {
					"error": "Increment must be a non-negative integer."
				}
			self.gameState.timeControls[1] = int(args["increment"])
		if args["mineCountPerSide"]:
			if not (args["mineCountPerSide"].isdigit() and int(args["mineCountPerSide"]) >= 0):
				return {
					"error": "Increment must be a non-negative integer."
				}
			self.gameState.mineCount = int(args["mineCountPerSide"]) * 2
		if args["movesUntilReset"]:
			if not (args["movesUntilReset"].isdigit() and int(args["movesUntilReset"]) >= 0):
				return {
					"error": "Increment must be a non-negative integer."
				}
			self.gameState.movesUntilReset = int(args["movesUntilReset"])

		await self.resetBoard(client, False)

		return {
			"success": True,
			"timeControls": self.gameState.timeControls,
			"mineCount": self.gameState.mineCount,
			"movesUntilReset": self.gameState.movesUntilReset
		}

	# async def getControls(self, client):
	# 	return {
	# 		"success": True,
	# 		"timeControls": self.gameState.timeControls
	# 	}


class Server():
	def __init__(self):
		self.clients = {} #<WebSocketServerProtocol>: lobby code
		self.lobbies = {} #lobby code: Lobby

	async def client_handler(self, client, path):
		print('New client', client)
		self.clients[client] = -1
		# self.clients.append(client)
		print(f' ({len(self.clients)} existing clients)')

		# Handle messages from this client
		try:
			while True:
				message = await self.receive(client)

				if message is None:
					del self.clients[client]
					# self.clients.remove(client)
					print('Client closed connection', client)
				elif "action" in message:
					response = {}
					try:
						if message["action"] == "joinLobby":
							response = self.joinLobby(message, client)
							if "lobbyCode" in response:
								await self.setBoard(client)
						elif message["action"] == "createLobby":
							response = self.createLobby(client)
							if "lobbyCode" in response:
								await self.setBoard(client)
						elif self.clients[client] == -1:
							response = {
								"error": "Not in a lobby"
							}
						elif "__" in message["action"]:
							response = {
								"error": "Can't invoke built-in functions."
							}
						elif "args" in message:
							response = await Lobby.__dict__[message["action"]](self.lobbies[self.clients[client]], client, message["args"])
						else:
							response = await Lobby.__dict__[message["action"]](self.lobbies[self.clients[client]], client)

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
			if not self.clients[client] == -1:
				lobbyOfClient = self.lobbies[self.clients[client]]
				lobbyOfClient.lobbyClients.remove(client)
				if len(lobbyOfClient.lobbyClients) == 0:
					print("Closing lobby", self.clients[client])
					del self.lobbies[self.clients[client]]
				clientGS = lobbyOfClient.gameState
				if client == clientGS.whitePlayer:
					clientGS.whitePlayer = None
					clientGS.__init__()
					await self.sendAll({
						"action": "whiteClaimed",
						"args": {
							"taken": False,
							"fen": clientGS.game.fen(),
							"mineCount": clientGS.mineCount
						}
					}, lobbyOfClient.lobbyClients)
				if client == clientGS.blackPlayer:
					clientGS.blackPlayer = None
					clientGS.__init__()
					await self.sendAll({
						"action": "blackClaimed",
						"args": {
							"taken": False,
							"fen": clientGS.game.fen(),
							"mineCount": clientGS.mineCount
						}
					}, lobbyOfClient.lobbyClients)
			del self.clients[client]
			# self.clients.remove(client)
			print('Client closed connection', client)

	async def send(self, client, message):
		await client.send(json.dumps(message))

	async def sendAll(self, message, lobbyClients, exclude=[]):
		for c in lobbyClients:
			if not c in exclude:
				await self.send(c, message)

	async def receive(self, client):
		return json.loads(await client.recv())

	def joinLobby(self, message, client):
		response = {}
		lobbyCode = message["args"]["lobbyCode"]
		if lobbyCode in self.lobbies:
			self.addToLobby(client, lobbyCode)
			response = {
				"lobbyCode": lobbyCode
			}
		else:
			response = {
				"error": "Lobby does not exist"
			}
		return response

	def createLobby(self, client):
		response = {}
		lobbyCode = ""
		while True:
			lobbyCode = "".join(random.choices(string.ascii_letters + string.digits, k=6))
			if not lobbyCode in self.lobbies:
				break
		self.addToLobby(client, lobbyCode)
		print("Created new lobby", lobbyCode)
		response = {
			"lobbyCode": lobbyCode
		}
		return response
	
	def addToLobby(self, client, lobbyCode):
		if not self.clients[client] == -1:
			lobbyOfClient = self.lobbies[self.clients[client]]
			lobbyOfClient.lobbyClients.remove(client)
			if len(lobbyOfClient.lobbyClients) == 0:
				print("Closing lobby", self.clients[client])
				del self.lobbies[self.clients[client]]
		self.clients[client] = lobbyCode
		if lobbyCode in self.lobbies:
			self.lobbies[lobbyCode].lobbyClients.append(client)
		else:
			self.lobbies[lobbyCode] = Lobby(self, [client])

	async def setBoard(self, client):
		clientGS = self.lobbies[self.clients[client]].gameState
		await self.send(client, {
			"action": "setBoard",
			"args": {
				"fen": clientGS.game.fen(),
				"mineCount": clientGS.mineCount,
				"prevMove": clientGS.prevMove,
				"timeControls": clientGS.timeControls,
				"movesUntilReset": clientGS.movesUntilReset,
				"whitePlayer": bool(clientGS.whitePlayer),
				"blackPlayer": bool(clientGS.blackPlayer)
			}
		})