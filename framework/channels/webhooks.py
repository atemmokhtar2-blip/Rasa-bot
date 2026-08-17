import hmac

class TelegramWebhookVerifier:
    def __init__(self, expected_secret: str | None): self.expected_secret = expected_secret
    def verify(self, provided_secret: str | None) -> bool:
        if not self.expected_secret: return True
        if not provided_secret: return False
        return hmac.compare_digest(provided_secret, self.expected_secret)
