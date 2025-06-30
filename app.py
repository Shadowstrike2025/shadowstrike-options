from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('welcome.html')

@app.route('/login')
def login():
    return "<h1>🔐 Login Page</h1><p>Authentication system coming soon!</p><a href='/'>← Back to Home</a>"

@app.route('/register')
def register():
    return "<h1>🆓 Register Page</h1><p>Registration system coming soon!</p><a href='/'>← Back to Home</a>"

@app.route('/status')
def status():
    return "<h1>✅ ShadowStrike Options Status</h1><p>Platform is LIVE and operational!</p><a href='/'>← Back to Home</a>"

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
