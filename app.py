
import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import logging
import yfinance as yf
from ta.momentum import RSIIndicator
from ta.trend import MACD, ADXIndicator
import pandas as pd
import numpy as np
from scipy.stats import norm
from flask_cors import CORS
from retry import retry
import firebase_admin
from firebase_admin import auth, credentials
import threading
import stripe
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
import requests
# Brevo config
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
BREVO_SENDER = {"name": "ShadowStrike Options", "email": "support@shadowstrike.com"}
BREVO_SMS_SENDER = "2154843692"
def send_email_async(to_email, subject, content):
    try:
        headers = {
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json"
        }
        data = {
            "sender": BREVO_SENDER,
            "to": [{"email": to_email}],
            "subject": subject,
            "htmlContent": content
        }
        response = requests.post("https://api.brevo.com/v3/smtp/email", json=data, headers=headers)
        logger.info(f"Brevo email to {to_email} sent: {response.status_code}")
    except Exception as e:
        logger.error(f"Brevo email error: {e}")
def send_sms(to_number, message):
    try:
        headers = {
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json"
        }
        data = {
            "sender": BREVO_SMS_SENDER,
            "recipient": to_number,
            "content": message,
            "type": "transactional"
        }
        response = requests.post("https://api.brevo.com/v1/transactionalSMS/sms", json=data, headers=headers)
        logger.info(f"Brevo SMS to {to_number} sent: {response.status_code}")
    except Exception as e:
        logger.error(f"Brevo SMS error: {e}")
# Initialize Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'shadowstrike-secret-2025')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///shadowstrike.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Email Configuration (SendGrid)
# Firebase Configuration
try:
    cred = credentials.Certificate("path/to/your/firebase-adminsdk.json")
    firebase_admin.initialize_app(cred)
except Exception as e:
    logger.error(f"Firebase initialization error: {e}")
# Stripe Configuration
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_demo_key')
app.config['STRIPE_PUBLIC_KEY'] = os.environ.get('STRIPE_PUBLIC_KEY', 'pk_test_demo_key')
# Fix for Render Postgres URL
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')
# Initialize extensions
db = SQLAlchemy(app)
CORS(app)
# Models
class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(100), nullable=False)
    symbol = db.Column(db.String(10), nullable=False)
    option_type = db.Column(db.String(10), nullable=False)
    strike_price = db.Column(db.Float, nullable=False)
    entry_price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    entry_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(10), default='open')
    broker_fee = db.Column(db.Float, default=0.65)
    stop_loss = db.Column(db.Float, nullable=True)
    target_price = db.Column(db.Float, nullable=True)
    exit_price = db.Column(db.Float, nullable=True)
    exit_date = db.Column(db.DateTime, nullable=True)
    pnl = db.Column(db.Float, nullable=True)
class EmailAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(100), nullable=False)
    alert_type = db.Column(db.String(50), nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    subject = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=True)
# Helper Functions
def send_email_async(to_email, subject, content):
    try:
                    from_email="support@shadowstrike.com",
            to_emails=to_email,
            subject=subject,
            html_content=content
        )
        response =         logger.info(f"Email sent to {to_email}: {response.status_code}")
    except Exception as e:
        logger.error(f"Email sending error: {e}")
def send_welcome_email(user_email, username):
    content = f"""
    <html>
    <body style="font-family: Arial; background: #1f2937; color: white; padding: 40px;">
        <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #065f46, #10b981); padding: 30px; border-radius: 15px;">
            <h1 style="color: #ffffff; text-align: center;"> Welcome to ShadowStrike Options!</h1>
            <h2>Hello {username}!</h2>
            <p>Your 30-day free trial has begun! After your trial, continue for just $49/month.</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="https://shadowstrike-options-2025.onrender.com/login" style="background: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                    Access Your Dashboard
                </a>
            </div>
        </div>
    </body>
    </html>
    """
    threading.Thread(target=send_email_async, args=(user_email, "Welcome to ShadowStrike Options!", content)).start()
@retry(tries=3, delay=2, backoff=2, logger=logger)
def fetch_stock_data(symbol, period="3mo", interval="1d"):
    try:
        stock = yf.Ticker(symbol)
        df = stock.history(period=period, interval=interval)
        if df.empty:
            raise ValueError("No data returned")
        return df
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        raise
def fetch_options_data(symbol):
    try:
        stock = yf.Ticker(symbol)
        expirations = stock.options
        options = []
        for exp in expirations[:5]:
            opt = stock.option_chain(exp)
            for type_, chain in [("CALL", opt.calls), ("PUT", opt.puts)]:
                for _, row in chain.iterrows():
                    days_to_expiry = (datetime.strptime(exp, "%Y-%m-%d") - datetime.now()).days
                    options.append({
                        "type": type_,
                        "strike": round(row["strike"], 2),
                        "expiration": exp,
                        "price": round(row["lastPrice"], 2),
                        "bid": round(row["bid"], 2),
                        "ask": round(row["ask"], 2),
                        "volume": int(row["volume"]) if pd.notna(row["volume"]) else 0,
                        "openInterest": int(row["openInterest"]) if pd.notna(row["openInterest"]) else 0,
                        "impliedVolatility": round(row["impliedVolatility"] * 100, 1) if pd.notna(row["impliedVolatility"]) else 20,
                        "daysToExpiry": days_to_expiry
                    })
        return sorted(options, key=lambda x: (x["expiration"], x["strike"]))
    except Exception as e:
        logger.error(f"Error fetching options for {symbol}: {e}")
        return []
def black_scholes(S, K, T, r, sigma, option_type="CALL"):
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        if option_type == "CALL":
            prob_itm = norm.cdf(d1)
        else:
            prob_itm = norm.cdf(-d1)
        return round(prob_itm * 100, 1), round((1 - prob_itm) * 100, 1)
    except:
        return 50, 50
def calculate_vertical_spread(symbol, options, spread_type="bull_call"):
    try:
        calls = [opt for opt in options if opt["type"] == "CALL"]
        puts = [opt for opt in options if opt["type"] == "PUT"]
        if spread_type == "bull_call":
            buy = min(calls, key=lambda x: x["strike"])
            sell = min([c for c in calls if c["strike"] > buy["strike"]], key=lambda x: x["strike"])
            max_profit = (sell["strike"] - buy["strike"] - (buy["price"] - sell["price"])) * 100
            max_loss = (buy["price"] - sell["price"]) * 100
            breakeven = buy["strike"] + (buy["price"] - sell["price"])
        elif spread_type == "bear_put":
            buy = max(puts, key=lambda x: x["strike"])
            sell = max([p for p in puts if p["strike"] < buy["strike"]], key=lambda x: x["strike"])
            max_profit = (buy["strike"] - sell["strike"] - (buy["price"] - sell["price"])) * 100
            max_loss = (buy["price"] - sell["price"]) * 100
            breakeven = buy["strike"] - (buy["price"] - sell["price"])
        return {
            "type": spread_type,
            "buy_strike": buy["strike"],
            "sell_strike": sell["strike"],
            "max_profit": round(max_profit, 2),
            "max_loss": round(max_loss, 2),
            "breakeven": round(breakeven, 2),
            "probability": buy["probability"]
        }
    except:
        return None
def analyze_stock(symbol):
    try:
        df = fetch_stock_data(symbol)
        if df is None:
            return {"symbol": symbol, "recommendation": "No data", "details": {}}
        # Technical indicators
        df['RSI'] = RSIIndicator(df['Close']).rsi()
        df['MACD'] = MACD(df['Close']).macd_diff()
        df['ADX'] = ADXIndicator(df['High'], df['Low'], df['Close']).adx()
                df['MA25'] = df['Close'].rolling(window=25).mean()
        df['MA50'] = df['Close'].rolling(window=50).mean()
        df['MA150'] = df['Close'].rolling(window=150).mean()
        # Volatility and stop-loss
        volatility = df['Close'].pct_change().rolling(window=30).std()[-1] * 100
        iv = fetch_options_data(symbol)[0]["impliedVolatility"] if fetch_options_data(symbol) else 20
        stop_loss = round(df['Close'].iloc[-1] * (1 - volatility / 100), 2)
        latest = df.iloc[-1]
        signals = []
        if latest['MACD'] > 0 and df['MACD'].iloc[-2] <= 0:
            signals.append("MACD Crossover (Bullish)")
        elif latest['MACD'] < 0 and df['MACD'].iloc[-2] >= 0:
            signals.append("MACD Crossover (Bearish)")
        if latest['PPO'] > 0 and df['PPO'].iloc[-2] <= 0:
                    elif latest['PPO'] < 0 and df['PPO'].iloc[-2] >= 0:
                    if latest['Close'] > latest['MA50'] and df['Close'].iloc[-2] <= df['MA50'].iloc[-2]:
            signals.append("Price/MA50 Crossover (Bullish)")
        recommendation = "Hold"
        if latest['RSI'] < 30 and latest['MACD'] > 0 and latest['ADX'] > 25:
            recommendation = "Call (Bullish)"
        elif latest['RSI'] > 70 and latest['MACD'] < 0 and latest['ADX'] > 25:
            recommendation = "Put (Bearish)"
        return {
            "symbol": symbol,
            "recommendation": recommendation,
            "details": {
                "RSI": round(latest['RSI'], 2),
                "MACD": round(latest['MACD'], 2),
                "ADX": round(latest['ADX'], 2),
                "MA25": round(latest['MA25'], 2),
                "MA50": round(latest['MA50'], 2),
                "MA150": round(latest['MA150'], 2),
                "Price": round(latest['Close'], 2),
                "Volatility": round(volatility, 2),
                "StopLoss": stop_loss
            },
            "signals": signals
        }
    except Exception as e:
        logger.error(f"Analysis error for {symbol}: {e}")
        return {"symbol": symbol, "recommendation": "Error", "details": {"Error": str(e)}}
# Routes
@app.route('/')
def index():
    return render_template('welcome.html')
@app.route('/init-db')
def initialize_database():
    try:
        db.drop_all()
        db.create_all()
        db.session.commit()
        logger.info("Database initialized successfully!")
        return """
        <html><body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; text-align: center; padding: 50px;">
        <h1> Database Initialized!</h1>
        <p>ShadowStrike Options database ready!</p>
        <a href="/login" style="background: #10b981; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Go to Login</a>
        </body></html>
        """
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        return """
        <html><body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; text-align: center; padding: 50px;">
        <h1> Database Initialization Failed</h1>
        <p>Check the logs for more details</p>
        <a href="/">Back to Home</a>
        </body></html>
        """
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            email = request.form.get('email')
            password = request.form.get('password')
            user = auth.sign_in_with_email_and_password(email, password)
            session['user_id'] = user['localId']
            session['email'] = user['email']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        except:
            flash('Invalid credentials', 'error')
    return render_template('login.html')
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            email = request.form.get('email')
            password = request.form.get('password')
            username = request.form.get('username')
            color = request.form.get('color', '#10b981')
            user = auth.create_user(email=email, password=password)
            db.session.add(User(
                id=user.uid,
                username=username,
                email=email,
                subscription_status='trial',
                trial_end_date=datetime.utcnow() + timedelta(days=30),
                color=color
            ))
            db.session.commit()
            send_welcome_email(email, username)
            flash('Registration successful! Check your email.', 'success')
            return redirect(url_for('login'))
        except:
            flash('Registration failed', 'error')
    return render_template('register.html')
@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        try:
            email = request.form.get('email')
            auth.send_password_reset_email(email)
            flash('Password reset email sent', 'success')
            return redirect(url_for('login'))
        except:
            flash('Email not found', 'error')
    return render_template('reset_password.html')
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please login to access the dashboard', 'error')
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user or (user.subscription_status == 'trial' and datetime.utcnow() > user.trial_end_date):
        flash('Your trial has expired. Please subscribe.', 'error')
        return redirect(url_for('subscribe'))
    market_status = get_market_status()
    top_movers = get_top_movers()
    trades = Trade.query.filter_by(user_id=session['user_id']).all()
    total_pnl = 0
    open_trades = 0
    enhanced_trades = []
    for trade in trades:
        if trade.status == 'open':
            open_trades += 1
            stock_data = get_stock_price(trade.symbol)
            current_stock_price = stock_data['price']
            options = fetch_options_data(trade.symbol)
            current_option = next((opt for opt in options if opt['type'] == trade.option_type and opt['strike'] == trade.strike_price), None)
            current_price = current_option['price'] if current_option else trade.entry_price
            pnl = (current_price - trade.entry_price) * trade.quantity * 100 - trade.broker_fee * trade.quantity
            trade.pnl = round(pnl, 2)
            enhanced_trades.append({
                'trade': trade,
                'current_stock_price': current_stock_price,
                'current_option_price': round(current_price, 2),
                'pnl': trade.pnl
            })
    return render_template('dashboard.html', 
                         user=user, 
                         trades=enhanced_trades, 
                         total_pnl=total_pnl,
                         open_trades=open_trades,
                         market_status=market_status,
                         top_movers=top_movers)
@app.route('/subscribe')
def subscribe():
    if 'user_id' not in session:
        flash('Please login to subscribe', 'error')
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if user.subscription_status == 'active':
        flash('You already have an active subscription!', 'info')
        return redirect(url_for('dashboard'))
    return render_template('subscribe.html', stripe_public_key=app.config['STRIPE_PUBLIC_KEY'])
@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': 'ShadowStrike Subscription'},
                    'unit_amount': 4900,
                    'recurring': {'interval': 'month'}
                },
                'quantity': 1
            }],
            mode='subscription',
            success_url='https://shadowstrike-options-2025.onrender.com/dashboard',
            cancel_url='https://shadowstrike-options-2025.onrender.com/subscribe'
        )
        user = User.query.get(session['user_id'])
        user.stripe_customer_id = session.customer
        user.stripe_subscription_id = session.subscription
        user.subscription_status = 'active'
        user.subscription_start_date = datetime.utcnow()
        user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
        db.session.commit()
        return jsonify({'id': session.id})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
@app.route('/market-data')
def market_data():
    market_status = get_market_status()
    top_movers = get_top_movers()
    return render_template('market_data.html', market_status=market_status, top_movers=top_movers)
@app.route('/api/top10', methods=['GET'])
def get_top10():
    symbols = ['SPY', 'QQQ', 'GLD', 'SLV']
    results = []
    for symbol in symbols:
        analysis = analyze_stock(symbol)
        options = fetch_options_data(symbol)
        for opt in options[:2]:
            S = analysis['details'].get('Price', 100)
            prob_itm, prob_otm = black_scholes(S, opt['strike'], opt['daysToExpiry']/365, 0.05, opt['impliedVolatility']/100, opt['type'])
            results.append({
                'symbol': symbol,
                'type': opt['type'],
                'strike': opt['strike'],
                'expiration': opt['expiration'],
                'price': opt['price'],
                'probabilityITM': prob_itm,
                'probabilityOTM': prob_otm,
                'signals': analysis['signals'],
                'score': prob_itm + (10 if analysis['signals'] else 0)
            })
        spread = calculate_vertical_spread(symbol, options)
        if spread:
            results.append({
                'symbol': symbol,
                'type': spread['type'],
                'buy_strike': spread['buy_strike'],
                'sell_strike': spread['sell_strike'],
                'max_profit': spread['max_profit'],
                'max_loss': spread['max_loss'],
                'breakeven': spread['breakeven'],
                'probabilityITM': spread['probability']
            })
    results.sort(key=lambda x: x['score'] if 'score' in x else x['probabilityITM'], reverse=True)
    # Send daily picks email (8-9 AM)
    now = datetime.now()
    if now.weekday() < 5 and 8 <= now.hour < 9:
        for user in User.query.filter_by(email_alerts_enabled=True).all():
            content = f"""
            <html>
            <body style="font-family: Arial; background: #1f2937; color: white; padding: 40px;">
                <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #065f46, #10b981); padding: 30px; border-radius: 15px;">
                    <h1 style="color: #ffffff; text-align: center;"> Daily Top 10 Picks</h1>
                    <ul>{''.join([f"<li>{item['symbol']} {item['type']} ${item['strike'] or item['buy_strike']}: {item['probabilityITM']}% ITM</li>" for item in results[:10]])}</ul>
                </div>
            </body>
            </html>
            """
            threading.Thread(target=send_email_async, args=(user.email, "ShadowStrike Daily Picks", content)).start()
    return jsonify(results[:10])
@app.route('/api/portfolio', methods=['GET', 'POST'])
def portfolio():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if request.method == 'POST':
        data = request.get_json()
        trade = Trade(
            user_id=session['user_id'],
            symbol=data['symbol'],
            option_type=data['type'],
            strike_price=data['strike'] or data['buy_strike'],
            entry_price=data['price'],
            quantity=data['contracts'],
            broker_fee=0.65 * data['contracts'],
            stop_loss=data.get('stop_loss'),
            target_price=data.get('target_price')
        )
        db.session.add(trade)
        db.session.commit()
        return jsonify({'message': 'Trade added'})
    trades = Trade.query.filter_by(user_id=session['user_id']).all()
    for trade in trades:
        if trade.status == 'open':
            options = fetch_options_data(trade.symbol)
            current = next((opt for opt in options if opt['type'] == trade.option_type and opt['strike'] == trade.strike_price), None)
            trade.current_price = current['price'] if current else trade.entry_price
            trade.pnl = (trade.current_price - trade.entry_price) * trade.quantity * 100 - trade.broker_fee
    return jsonify([{
        'symbol': t.symbol,
        'type': t.option_type,
        'strike': t.strike_price,
        'entry_price': t.entry_price,
        'current_price': t.current_price,
        'pnl': t.pnl,
        'contracts': t.quantity,
        'stop_loss': t.stop_loss,
        'target_price': t.target_price
    } for t in trades])
@app.route('/api/scanner', methods=['GET'])
def scanner():
    symbols = ['SPY', 'QQQ', 'GLD', 'SLV']
    results = []
    for symbol in symbols:
        analysis = analyze_stock(symbol)
        options = fetch_options_data(symbol)
        for opt in options[:2]:
            S = analysis['details'].get('Price', 100)
            prob_itm, prob_otm = black_scholes(S, opt['strike'], opt['daysToExpiry']/365, 0.05, opt['impliedVolatility']/100, opt['type'])
            results.append({
                'symbol': symbol,
                'type': opt['type'],
                'strike': opt['strike'],
                'expiration': opt['expiration'],
                'price': opt['price'],
                'probabilityITM': prob_itm,
                'probabilityOTM': prob_otm,
                'recommendation': analysis['recommendation']
            })
        spread = calculate_vertical_spread(symbol, options)
        if spread:
            results.append({
                'symbol': symbol,
                'type': spread['type'],
                'buy_strike': spread['buy_strike'],
                'sell_strike': spread['sell_strike'],
                'max_profit': spread['max_profit'],
                'max_loss': spread['max_loss'],
                'breakeven': spread['breakeven'],
                'probabilityITM': spread['probability']
            })
    results.sort(key=lambda x: x['probabilityITM'], reverse=True)
    return jsonify(results[:10])
@app.route('/api/trade-scenario', methods=['POST'])
def trade_scenario():
    data = request.get_json()
    symbol = data.get('symbol')
    target_price = data.get('target_price')
    options = fetch_options_data(symbol)
    results = []
    for opt in options[:5]:
        S = target_price
        prob_itm, prob_otm = black_scholes(S, opt['strike'], opt['daysToExpiry']/365, 0.05, opt['impliedVolatility']/100, opt['type'])
        results.append({
            'symbol': symbol,
            'type': opt['type'],
            'strike': opt['strike'],
            'expiration': opt['expiration'],
            'price': opt['price'],
            'probabilityITM': prob_itm,
            'probabilityOTM': prob_otm
        })
    return jsonify(results)
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))
@app.route('/mobile-demo')
def mobile_demo():
    return render_template('mobile_demo.html')
# HTML Templates
welcome_html = """
<!DOCTYPE html>
<html><head><title>ShadowStrike Options</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gradient-to-br from-gray-900 to-emerald-900 text-white font-sans flex items-center justify-center min-h-screen">
    <div class="max-w-2xl mx-auto bg-gray-800/50 p-10 rounded-2xl shadow-2xl text-center">
        <h1 class="text-4xl font-bold text-emerald-400 mb-6"> ShadowStrike Options</h1>
        <p class="text-lg text-emerald-100 mb-8">Elite Trading Platform for Options Traders</p>
        <div class="space-y-4">
            <a href="/login" class="block bg-emerald-500 text-white py-3 px-6 rounded-lg font-bold hover:bg-emerald-600 transition">Login</a>
            <a href="/register" class="block bg-emerald-500 text-white py-3 px-6 rounded-lg font-bold hover:bg-emerald-600 transition">Start 30-Day Trial</a>
            <a href="/mobile-demo" class="block bg-emerald-500 text-white py-3 px-6 rounded-lg font-bold hover:bg-emerald-600 transition">Mobile Demo</a>
        </div>
    </div>
</body></html>
"""
login_html = """
<!DOCTYPE html>
<html><head><title>Login - ShadowStrike Options</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gradient-to-br from-gray-900 to-emerald-900 text-white font-sans flex items-center justify-center min-h-screen">
    <div class="max-w-md mx-auto bg-gray-800/50 p-8 rounded-2xl shadow-2xl">
        <h1 class="text-3xl font-bold text-emerald-400 text-center mb-6"> ShadowStrike Options</h1>
        <h2 class="text-xl text-center mb-6">Login</h2>
        <form method="POST" class="space-y-4">
            <div>
                <label class="block text-emerald-300">Email</label>
                <input name="email" type="email" class="w-full p-3 rounded-lg bg-gray-700 border border-emerald-500 text-white" required>
            </div>
            <div>
                <label class="block text-emerald-300">Password</label>
                <input name="password" type="password" class="w-full p-3 rounded-lg bg-gray-700 border border-emerald-500 text-white" required>
            </div>
            <button type="submit" class="w-full bg-emerald-500 text-white py-3 rounded-lg font-bold hover:bg-emerald-600">Login</button>
        </form>
        <p class="text-center mt-4">
            <a href="/reset-password" class="text-emerald-300 hover:underline">Forgot Password?</a> | 
            <a href="/register" class="text-emerald-300 hover:underline">Register</a>
        </p>
    </div>
</body></html>
"""
register_html = """
<!DOCTYPE html>
<html><head><title>Register - ShadowStrike Options</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gradient-to-br from-gray-900 to-emerald-900 text-white font-sans flex items-center justify-center min-h-screen">
    <div class="max-w-md mx-auto bg-gray-800/50 p-8 rounded-2xl shadow-2xl">
        <h1 class="text-3xl font-bold text-emerald-400 text-center mb-6"> ShadowStrike Options</h1>
        <h2 class="text-xl text-center mb-6">Register</h2>
        <form method="POST" class="space-y-4">
            <div>
                <label class="block text-emerald-300">Username</label>
                <input name="username" class="w-full p-3 rounded-lg bg-gray-700 border border-emerald-500 text-white" required>
            </div>
            <div>
                <label class="block text-emerald-300">Email</label>
                <input name="email" type="email" class="w-full p-3 rounded-lg bg-gray-700 border border-emerald-500 text-white" required>
            </div>
            <div>
                <label class="block text-emerald-300">Password</label>
                <input name="password" type="password" class="w-full p-3 rounded-lg bg-gray-700 border border-emerald-500 text-white" required>
            </div>
            <div>
                <label class="block text-emerald-300">Theme Color (e.g., #10b981)</label>
                <input name="color" class="w-full p-3 rounded-lg bg-gray-700 border border-emerald-500 text-white" value="#10b981">
            </div>
            <button type="submit" class="w-full bg-emerald-500 text-white py-3 rounded-lg font-bold hover:bg-emerald-600">Start 30-Day Trial</button>
        </form>
        <p class="text-center mt-4">
            <a href="/login" class="text-emerald-300 hover:underline">Already have an account?</a>
        </p>
    </div>
</body></html>
"""
reset_password_html = """
<!DOCTYPE html>
<html><head><title>Reset Password - ShadowStrike Options</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gradient-to-br from-gray-900 to-emerald-900 text-white font-sans flex items-center justify-center min-h-screen">
    <div class="max-w-md mx-auto bg-gray-800/50 p-8 rounded-2xl shadow-2xl">
        <h1 class="text-3xl font-bold text-emerald-400 text-center mb-6"> Reset Password</h1>
        <form method="POST" class="space-y-4">
            <div>
                <label class="block text-emerald-300">Email</label>
                <input name="email" type="email" class="w-full p-3 rounded-lg bg-gray-700 border border-emerald-500 text-white" required>
            </div>
            <button type="submit" class="w-full bg-emerald-500 text-white py-3 rounded-lg font-bold hover:bg-emerald-600">Send Reset Email</button>
        </form>
        <p class="text-center mt-4">
            <a href="/login" class="text-emerald-300 hover:underline">Back to Login</a>
        </p>
    </div>
</body></html>
"""
dashboard_html = """
<!DOCTYPE html>
<html><head><title>Dashboard - ShadowStrike Options</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gradient-to-br from-gray-900 to-emerald-900 text-white font-sans">
    <div class="max-w-5xl mx-auto p-6">
        <h1 class="text-3xl font-bold text-emerald-400 mb-6"> ShadowStrike Options - Dashboard</h1>
        <p class="text-emerald-100">Welcome {{ user.username }}! ({{ user.subscription_status }} - {% if user.subscription_status == 'trial' %}{{ user.days_left_in_trial() }} days left{% else %}Active{% endif %})</p>
        {% if user.subscription_status == 'trial' and user.days_left_in_trial() <= 7 %}
        <div class="bg-red-500/20 p-4 rounded-lg mb-6">
            <p class="text-red-300"> Trial expires in {{ user.days_left_in_trial() }} days! <a href="/subscribe" class="text-emerald-300 hover:underline">Subscribe now</a></p>
        </div>
        {% endif %}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="bg-gray-800/50 p-6 rounded-lg">
                <h2 class="text-xl font-semibold text-emerald-300 mb-4">Market Status</h2>
                <p>Status: <strong>{{ market_status.status }}</strong></p>
                <p>Next Open: {{ market_status.next_open }}</p>
            </div>
            <div class="bg-gray-800/50 p-6 rounded-lg">
                <h2 class="text-xl font-semibold text-emerald-300 mb-4">Portfolio Summary</h2>
                <p>Total P&L: ${{ total_pnl|round(2) }}</p>
                <p>Open Trades: {{ open_trades }}</p>
            </div>
        </div>
        <h2 class="text-xl font-semibold text-emerald-300 mt-6 mb-4">Top Market Movers</h2>
        <div class="overflow-x-auto">
            <table class="w-full border-collapse">
                <thead>
                    <tr class="bg-emerald-500/30">
                        <th class="p-3 text-left">Symbol</th>
                        <th class="p-3 text-left">Price</th>
                        <th class="p-3 text-left">Change</th>
                        <th class="p-3 text-left">% Change</th>
                    </tr>
                </thead>
                <tbody>
                    {% for mover in top_movers %}
                    <tr class="bg-gray-800/30">
                        <td class="p-3">{{ mover.symbol }}</td>
                        <td class="p-3">${{ mover.price|round(2) }}</td>
                        <td class="p-3 {{ 'text-emerald-400' if mover.change >= 0 else 'text-red-400' }}">{{ mover.change|round(2) }}</td>
                        <td class="p-3 {{ 'text-emerald-400' if mover.change_percent >= 0 else 'text-red-400' }}">{{ mover.change_percent|round(2) }}%</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        <h2 class="text-xl font-semibold text-emerald-300 mt-6 mb-4">Your Trades</h2>
        <div class="overflow-x-auto">
            <table class="w-full border-collapse">
                <thead>
                    <tr class="bg-emerald-500/30">
                        <th class="p-3 text-left">Symbol</th>
                        <th class="p-3 text-left">Type</th>
                        <th class="p-3 text-left">Strike</th>
                        <th class="p-3 text-left">Entry Price</th>
                        <th class="p-3 text-left">Current Price</th>
                        <th class="p-3 text-left">P&L</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item in trades %}
                    <tr class="bg-gray-800/30">
                        <td class="p-3">{{ item.trade.symbol }}</td>
                        <td class="p-3">{{ item.trade.option_type }}</td>
                        <td class="p-3">${{ item.trade.strike_price|round(2) }}</td>
                        <td class="p-3">${{ item.trade.entry_price|round(2) }}</td>
                        <td class="p-3">${{ item.current_option_price|round(2) }}</td>
                        <td class="p-3 {{ 'text-emerald-400' if item.pnl >= 0 else 'text-red-400' }}">{{ item.pnl|round(2) }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        <div class="mt-6 space-x-4">
            <a href="/logout" class="text-red-400 hover:underline">Logout</a>
            <a href="/subscribe" class="text-emerald-300 hover:underline">Subscribe</a>
            <a href="/mobile-demo" class="text-emerald-300 hover:underline">Mobile App</a>
        </div>
    </div>
</body></html>
"""
subscribe_html = """
<!DOCTYPE html>
<html><head><title>Subscribe - ShadowStrike Options</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://js.stripe.com/v3/"></script>
</head>
<body class="bg-gradient-to-br from-gray-900 to-emerald-900 text-white font-sans flex items-center justify-center min-h-screen">
    <div class="max-w-2xl mx-auto bg-gray-800/50 p-10 rounded-2xl shadow-2xl text-center">
        <h1 class="text-3xl font-bold text-emerald-400 mb-6"> Continue Your Trading Success</h1>
        <p class="text-lg text-emerald-100 mb-8">Don't lose access to profitable trading opportunities!</p>
        <div class="bg-red-500/20 p-6 rounded-lg mb-8">
            <h2 class="text-xl text-red-300"> {{ user.days_left_in_trial() }} Days Left in Trial</h2>
        </div>
        <div class="text-4xl font-bold text-emerald-400 mb-8">$49/month</div>
        <p class="text-emerald-100 mb-8">Cancel anytime  No long-term contracts</p>
        <div class="bg-emerald-500/10 p-6 rounded-lg mb-8">
            <h3 class="text-xl text-emerald-300 mb-4">What You Keep:</h3>
            <ul class="text-emerald-100 space-y-2">
                <li> Real-time options analysis with live market data</li>
                <li> Advanced options scanner for high-probability trades</li>
                <li> Portfolio tracking with live P&L calculations</li>
                <li> Daily trading alerts and opportunities</li>
                <li> Mobile app access for trading on-the-go</li>
            </ul>
        </div>
        <div>
            <h3 class="text-xl text-emerald-300 mb-4">Choose Payment Method:</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <button onclick="checkout('stripe')" class="bg-blue-600 text-white py-4 px-6 rounded-lg font-bold hover:bg-blue-700"> Pay with Card</button>
                <button onclick="alert('PayPal payment demo')" class="bg-blue-800 text-white py-4 px-6 rounded-lg font-bold hover:bg-blue-900"> PayPal</button>
            </div>
            <p class="text-emerald-100 mt-4 text-sm"> Secure payment processing</p>
        </div>
        <p class="mt-6"><a href="/dashboard" class="text-emerald-300 hover:underline"> Continue Trial ({{ user.days_left_in_trial() }} days left)</a></p>
        <script>
            const stripe = Stripe('{{ stripe_public_key }}');
            function checkout(method) {
                if (method === 'stripe') {
                    fetch('/create-checkout-session', { method: 'POST' })
                        .then(response => response.json())
                        .then(session => stripe.redirectToCheckout({ sessionId: session.id }))
                        .catch(error => alert('Error: ' + error));
                }
            }
        </script>
    </div>
</body></html>
"""
market_data_html = """
<!DOCTYPE html>
<html><head><title>Market Data - ShadowStrike Options</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gradient-to-br from-gray-900 to-emerald-900 text-white font-sans">
    <div class="max-w-5xl mx-auto p-6">
        <h1 class="text-3xl font-bold text-emerald-400 mb-6"> Live Market Data</h1>
        <p>Market Status: <strong>{{ market_status.status }}</strong></p>
        <p>Next Open: {{ market_status.next_open }}</p>
        <h2 class="text-xl font-semibold text-emerald-300 mt-6 mb-4">Top Market Movers</h2>
        <div class="overflow-x-auto">
            <table class="w-full border-collapse">
                <thead>
                    <tr class="bg-emerald-500/30">
                        <th class="p-3 text-left">Symbol</th>
                        <th class="p-3 text-left">Price</th>
                        <th class="p-3 text-left">Change</th>
                        <th class="p-3 text-left">% Change</th>
                    </tr>
                </thead>
                <tbody>
                    {% for mover in top_movers %}
                    <tr class="bg-gray-800/30">
                        <td class="p-3">{{ mover.symbol }}</td>
                        <td class="p-3">${{ mover.price|round(2) }}</td>
                        <td class="p-3 {{ 'text-emerald-400' if mover.change >= 0 else 'text-red-400' }}">{{ mover.change|round(2) }}</td>
                        <td class="p-3 {{ 'text-emerald-400' if mover.change_percent >= 0 else 'text-red-400' }}">{{ mover.change_percent|round(2) }}%</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        <p class="mt-6">
            <a href="/" class="text-emerald-300 hover:underline">Home</a> | 
            <a href="/login" class="text-emerald-300 hover:underline">Login</a>
        </p>
    </div>
</body></html>
"""
mobile_demo_html = """
<!DOCTYPE html>
<html><head><title>Mobile Demo - ShadowStrike Options</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gradient-to-br from-gray-900 to-emerald-900 text-white font-sans flex items-center justify-center min-h-screen">
    <div class="max-w-md mx-auto bg-gray-800/50 p-8 rounded-2xl shadow-2xl text-center">
        <h1 class="text-3xl font-bold text-emerald-400 mb-6"> ShadowStrike Mobile Demo</h1>
        <p class="text-emerald-100 mb-6">Experience our mobile app with the same powerful features!</p>
        <div class="bg-emerald-500/10 p-6 rounded-lg mb-6">
            <p class="text-emerald-100">Download the ShadowStrike app for iOS or Android to trade on-the-go.</p>
            <p class="text-emerald-100 mt-4">Full app coming soon!</p>
        </div>
        <a href="/login" class="block bg-emerald-500 text-white py-3 px-6 rounded-lg font-bold hover:bg-emerald-600">Back to Login</a>
    </div>
</body></html>
"""
os.makedirs("templates", exist_ok=True)
for name, content in [
    ("welcome.html", welcome_html),
    ("login.html", login_html),
    ("register.html", register_html),
    ("reset_password.html", reset_password_html),
    ("dashboard.html", dashboard_html),
    ("subscribe.html", subscribe_html),
    ("market_data.html", market_data_html),
    ("mobile_demo.html", mobile_demo_html)
]:
    with open(f"templates/{name}", "w") as f:
        f.write(content)
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)