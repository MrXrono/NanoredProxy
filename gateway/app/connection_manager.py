class ConnectionManager:
    def __init__(self):
        self.connections = {}

    def add(self, key, value):
        self.connections[key] = value

    def get(self, key):
        return self.connections.get(key)

    def remove(self, key):
        self.connections.pop(key, None)


connection_manager = ConnectionManager()
