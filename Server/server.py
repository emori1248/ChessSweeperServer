import asyncio

# The set of clients connected to this server. It is used to distribute
# messages.
clients = {} #: {websocket: name}

async def client_handler(websocket, path):
    print('New client', websocket)
    print(' ({} existing clients)'.format(len(clients)))


    identifier = await websocket.recv()
    clients[websocket] = identifier
    for client, _ in clients.items():
        await client.send(identifier)

    # Handle messages from this client
    while True:
        message = await websocket.recv()
        if message is None:
            their_name = clients[websocket]
            del clients[websocket]
            print('Client closed connection', websocket)
            for client, _ in clients.items():
                await client.send(their_name)
            break

        # Send message to all clients
        for client, _ in clients.items():
            await client.send('{}: {}'.format(identifier, message))
