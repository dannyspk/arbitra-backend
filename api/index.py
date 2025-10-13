from src.arbitrage.web import app

# Vercel serverless handler
def handler(request, context):
    return app(request, context)
