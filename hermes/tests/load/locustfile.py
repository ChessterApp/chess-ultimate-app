"""Locust load test simulating 50 concurrent coaching sessions.

Realistic scenarios: chat messages, position analysis, opening queries.

Run:
    locust -f tests/load/locustfile.py --host http://localhost:8642
"""

import random
import uuid

from locust import HttpUser, task, between, tag

SAMPLE_FENS = [
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3",
    "rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6",
    "r1bq1rk1/2ppbppp/p1n2n2/1p2p3/4P3/1B3N2/PPPP1PPP/RNBQR1K1 w - - 0 9",
    "8/8/8/4k3/8/8/8/4K2R w - - 0 1",
]

CHAT_MESSAGES = [
    "What is the best response to 1.e4?",
    "Explain the Sicilian Defense",
    "How do I improve my endgame?",
    "What are the key ideas in the Italian Game?",
    "Analyze my position",
    "What opening should I play as black?",
    "Help me with my pawn structure",
    "What are common tactical patterns?",
    "How do I avoid time trouble?",
    "Teach me about the Ruy Lopez",
]


class ChessCoachUser(HttpUser):
    """Simulates a chess student using the coaching API."""

    wait_time = between(2, 8)  # 2-8 seconds between requests

    def on_start(self):
        """Set up user identity and create a session."""
        self.user_id = f"load-test-{uuid.uuid4().hex[:8]}"
        self.headers = {"X-User-Id": self.user_id}
        self.session_id = None

        # Create a session
        resp = self.client.post(
            "/api/coach/sessions",
            headers=self.headers,
            json={},
        )
        if resp.status_code == 200:
            self.session_id = resp.json().get("id")

    @tag("chat")
    @task(5)
    def send_chat_message(self):
        """Send a coaching question."""
        message = random.choice(CHAT_MESSAGES)
        payload = {"message": message}
        if self.session_id:
            payload["session_id"] = self.session_id

        self.client.post(
            "/api/coach/chat",
            headers=self.headers,
            json=payload,
            name="/api/coach/chat",
        )

    @tag("analyze")
    @task(3)
    def analyze_position(self):
        """Send a position for analysis."""
        fen = random.choice(SAMPLE_FENS)
        payload = {
            "message": "Analyze this position and suggest the best plan",
            "fen": fen,
        }
        if self.session_id:
            payload["session_id"] = self.session_id

        self.client.post(
            "/api/coach/chat",
            headers=self.headers,
            json=payload,
            name="/api/coach/chat [analyze]",
        )

    @tag("openings")
    @task(2)
    def ask_about_opening(self):
        """Ask about chess openings."""
        openings = [
            "Sicilian Defense", "Ruy Lopez", "Italian Game",
            "Queen's Gambit", "French Defense", "Caro-Kann",
        ]
        payload = {
            "message": f"Tell me about the {random.choice(openings)}",
        }
        if self.session_id:
            payload["session_id"] = self.session_id

        self.client.post(
            "/api/coach/chat",
            headers=self.headers,
            json=payload,
            name="/api/coach/chat [openings]",
        )

    @tag("profile")
    @task(1)
    def check_profile(self):
        """Fetch user profile."""
        self.client.get(
            "/api/coach/profile",
            headers=self.headers,
            name="/api/coach/profile",
        )

    @tag("sessions")
    @task(1)
    def list_sessions(self):
        """List user sessions."""
        self.client.get(
            "/api/coach/sessions",
            headers=self.headers,
            name="/api/coach/sessions",
        )

    @tag("health")
    @task(1)
    def check_health(self):
        """Hit the health endpoint."""
        self.client.get("/health", name="/health")

    @tag("usage")
    @task(1)
    def check_usage(self):
        """Check usage endpoint."""
        self.client.get(
            "/api/coach/usage",
            headers=self.headers,
            name="/api/coach/usage",
        )
