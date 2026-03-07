class SessionManager:
    def __init__(self):
        self.sessions = {}

    def set(self, key, value):
        self.sessions[key] = value

    def get(self, key):
        return self.sessions.get(key)

session_manager = SessionManager()
