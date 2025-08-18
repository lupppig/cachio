
class ErrorParseScheme(Exception):
    def __init__(self, message: str,*args):
        self.message = message
        super().__init__(*args)