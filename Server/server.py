import asyncio
import websockets
import json
import traceback

# The set of clients connected to this server. It is used to distribute
# messages.


class Api():
	def __init__(self, server):
		self.server = server

	async def echoAll(self, args):
		for client in self.server.clients.keys():
			await self.server.send(client, args)


class Server():
	def __init__(self):
		self.clients = {}
		self.fen = ''
		self.whitePlayer = None
		self.blackPlayer = None

	async def client_handler(self, websocket, path):
		sess = Api(self)
		print('New client', sess)
		self.clients[sess] = websocket
		print(f' ({len(self.clients)} existing clients)')

		# Handle messages from this client
		try:
			while True:
				message = await self.receive(sess)

				if message is None:
					del self.clients[sess]
					print('Client closed connection', sess)
				elif "action" in message:
					response = {}
					try:
						if "args" in message:
							await Api.__dict__[message["action"]](sess, message["args"])
						else:
							await Api.__dict__[message["action"]](sess)
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
						await self.send(sess, response)
				else:
					# Only supports action format
					await self.send(sess, {"error": "Invalid packet format"})

		except websockets.exceptions.ConnectionClosedOK:
			del self.clients[sess]
			print('Client closed connection', sess)

	async def send(self, sess, message):
		await self.clients[sess].send(json.dumps(message))

	async def receive(self, sess):
		return json.loads(await self.clients[sess].recv())
