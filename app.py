# Payment Routes (Add these just before if __name__ == '__main__':)

@app.route('/subscribe')
def subscribe():
    """Subscription page with Stripe and PayPal options"""
    if 'user_id' not in session:
        flash('Please login to subscribe', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('login'))
    
    # If already subscribed, redirect to dashboard
    if user.subscription_status == 'active':
        flash('You already have an active subscription!', 'info')
        return redirect(url_for('dashboard'))
    
    try:
        return render_template('subscribe.html', 
                             user=user,
                             stripe_public_key=app.config['STRIPE_PUBLIC_KEY'],
                             days_left=user.days_left_in_trial())
    except Exception as e:
        logger.error(f"Error rendering subscribe.html: {e}")
        return f"""
        <!DOCTYPE html>
        <html><head><title>Subscribe - ShadowStrike Options</title></head>
        <body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; padding: 50px;">
        <div style="max-width: 600px; margin: 0 auto; background: rgba(6, 95, 70, 0.3); padding: 30px; border-radius: 15px;">
            <h1 style="color: #10b981; text-align: center;">💳 Subscribe to ShadowStrike Options</h1>
            <div style="text-align: center; margin: 30px 0;">
                <h2 style="color: #ffffff;">Continue Your Trading Success</h2>
                <p style="color: #a7f3d0;">Trial expires in {user.days_left_in_trial()} days</p>
                <div style="font-size: 2em; color: #10b981; margin: 20px 0;">$49/month</div>
                <p style="color: #a7f3d0;">Cancel anytime • No long-term contracts</p>
            </div>
            
            <div style="background: rgba(16, 185, 129, 0.1); padding: 20px; border-radius: 10px; margin: 20px 0;">
                <h3 style="color: #10b981;">What You Get:</h3>
                <ul style="color: #a7f3d0;">
                    <li>📊 Real-time options analysis</li>
                    <li>🎯 Advanced options scanner</li>
                    <li>📈 Portfolio tracking with live P&L</li>
                    <li>📧 Daily trading alerts</li>
                    <li>📱 Mobile app access</li>
                    <li>🤖 AI-powered probability calculations</li>
                </ul>
            </div>
            
            <div style="text-align: center;">
                <a href="/dashboard" style="background: #10b981; color: white; padding: 12px 25px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                    Continue Trial ({user.days_left_in_trial()} days left)
                </a>
            </div>
        </div>
        </body></html>
        """

@app.route('/create-stripe-subscription', methods=['POST'])
def create_stripe_subscription_route():
    """Handle Stripe subscription creation"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    try:
        payment_method_id = request.json.get('payment_method_id')
        if not payment_method_id:
            return jsonify({'error': 'Payment method required'}), 400
        
        subscription = create_stripe_subscription(user, payment_method_id)
        if subscription:
            # Record transaction
            transaction = PaymentTransaction(
                user_id=user.id,
                transaction_id=subscription.id,
                payment_method='stripe',
                amount=49.00,
                status='pending',
                description='Monthly subscription setup'
            )
            db.session.add(transaction)
            db.session.commit()
            
            flash('Subscription created successfully! You will be billed when your trial ends.', 'success')
            return jsonify({'success': True, 'subscription_id': subscription.id})
        else:
            return jsonify({'error': 'Failed to create subscription'}), 500
            
    except Exception as e:
        logger.error(f"Error creating Stripe subscription: {e}")
        return jsonify({'error': 'Subscription creation failed'}), 500

@app.route('/create-paypal-subscription', methods=['POST'])
def create_paypal_subscription_route():
    """Handle PayPal subscription creation"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    try:
        # Create PayPal subscription (simplified for demo)
        # In production, you'd create actual PayPal subscription plans
        
        user.payment_method = 'paypal'
        user.subscription_status = 'trial'  # Keep trial status until trial ends
        
        # Record transaction
        transaction = PaymentTransaction(
            user_id=user.id,
            transaction_id=f'paypal_{user.id}_{int(datetime.now().timestamp())}',
            payment_method='paypal',
            amount=49.00,
            status='pending',
            description='PayPal subscription setup'
        )
        db.session.add(transaction)
        db.session.commit()
        
        flash('PayPal subscription set up successfully! You will be billed when your trial ends.', 'success')
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error creating PayPal subscription: {e}")
        return jsonify({'error': 'PayPal subscription creation failed'}), 500

@app.route('/subscription-success')
def subscription_success():
    """Subscription success page"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('login'))
    
    return f"""
    <!DOCTYPE html>
    <html><head><title>Subscription Success - ShadowStrike Options</title></head>
    <body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; padding: 50px;">
    <div style="max-width: 600px; margin: 0 auto; background: rgba(6, 95, 70, 0.3); padding: 40px; border-radius: 15px; text-align: center;">
        <h1 style="color: #10b981;">🎉 Subscription Activated!</h1>
        <p style="font-size: 1.2em; margin: 20px 0;">Thank you, {user.username}!</p>
        <p style="color: #a7f3d0;">Your subscription has been set up successfully.</p>
        
        <div style="background: rgba(16, 185, 129, 0.2); padding: 20px; border-radius: 10px; margin: 30px 0;">
            <h3 style="color: #10b981;">What happens next:</h3>
            <ul style="color: #a7f3d0; text-align: left; display: inline-block;">
                <li>Continue enjoying your free trial ({user.days_left_in_trial()} days left)</li>
                <li>Your first payment of $49 will be charged when trial ends</li>
                <li>You'll receive email confirmation and receipts</li>
                <li>Cancel anytime from your dashboard</li>
            </ul>
        </div>
        
        <a href="/dashboard" style="background: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 1.1em;">
            Continue to Dashboard
        </a>
    </div>
    </body></html>
    """

@app.route('/billing')
def billing():
    """Billing and subscription management"""
    if 'user_id' not in session:
        flash('Please login to view billing', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('login'))
    
    # Get payment history
    transactions = PaymentTransaction.query.filter_by(user_id=user.id).order_by(PaymentTransaction.transaction_date.desc()).limit(10).all()
    
    return f"""
    <!DOCTYPE html>
    <html><head><title>Billing - ShadowStrike Options</title></head>
    <body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; padding: 50px;">
    <div style="max-width: 800px; margin: 0 auto;">
        <h1 style="color: #10b981; text-align: center;">💳 Billing & Subscription</h1>
        
        <!-- Current Subscription -->
        <div style="background: rgba(6, 95, 70, 0.3); padding: 30px; border-radius: 15px; margin: 20px 0;">
            <h2 style="color: #10b981;">Current Plan</h2>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0;">
                <div>
                    <strong>Status:</strong> {user.subscription_status.title()}<br>
                    <strong>Payment Method:</strong> {user.payment_method.title() if user.payment_method else 'None'}<br>
                    {'<strong>Trial Ends:</strong> ' + user.trial_end_date.strftime('%B %d, %Y') if user.subscription_status == 'trial' else ''}
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 2em; color: #10b981; font-weight: bold;">
                        {'FREE' if user.subscription_status == 'trial' else '$49/month'}
                    </div>
                    <div style="color: #a7f3d0; font-size: 0.9em;">
                        {f"{user.days_left_in_trial()} days left in trial" if user.subscription_status == 'trial' else "Next billing: " + (datetime.now() + timedelta(days=30)).strftime('%B %d')}
                    </div>
                </div>
            </div>
            
            <div style="text-align: center; margin-top: 20px;">
                {'<a href="/subscribe" style="background: #10b981; color: white; padding: 12px 25px; text-decoration: none; border-radius: 8px; font-weight: bold;">Set Up Billing</a>' if user.subscription_status == 'trial' and not user.payment_method else ''}
                <a href="/cancel-subscription" style="background: #ef4444; color: white; padding: 12px 25px; text-decoration: none; border-radius: 8px; font-weight: bold; margin-left: 10px;">Cancel Subscription</a>
            </div>
        </div>
        
        <!-- Payment History -->
        <div style="background: rgba(6, 95, 70, 0.3); padding: 30px; border-radius: 15px; margin: 20px 0;">
            <h2 style="color: #10b981;">Payment History</h2>
            {''.join([f'''
            <div style="background: rgba(16, 185, 129, 0.1); padding: 15px; border-radius: 10px; margin: 10px 0; display: flex; justify-content: space-between;">
                <div>
                    <strong>{transaction.description}</strong><br>
                    <small style="color: #a7f3d0;">{transaction.transaction_date.strftime('%B %d, %Y')} • {transaction.payment_method.title()}</small>
                </div>
                <div style="text-align: right;">
                    <strong>${transaction.amount:.2f}</strong><br>
                    <small style="color: {'#10b981' if transaction.status == 'completed' else '#6b7280'};">{transaction.status.title()}</small>
                </div>
            </div>
            ''' for transaction in transactions]) if transactions else '<p style="color: #a7f3d0; text-align: center; padding: 20px;">No payment history yet</p>'}
        </div>
        
        <div style="text-align: center;">
            <a href="/dashboard" style="color: #10b981; text-decoration: none;">← Back to Dashboard</a>
        </div>
    </div>
    </body></html>
    """

@app.route('/cancel-subscription', methods=['GET', 'POST'])
def cancel_subscription():
    """Cancel subscription"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            # Cancel Stripe subscription if exists
            if user.stripe_subscription_id:
                stripe.Subscription.delete(user.stripe_subscription_id)
            
            # Update user status
            user.subscription_status = 'cancelled'
            user.subscription_end_date = user.trial_end_date if user.subscription_status == 'trial' else datetime.utcnow()
            
            db.session.commit()
            
            flash('Subscription cancelled successfully. You can continue using the platform until your current period ends.', 'info')
            return redirect(url_for('billing'))
            
        except Exception as e:
            logger.error(f"Error cancelling subscription: {e}")
            flash('Error cancelling subscription. Please contact support.', 'error')
    
    return f"""
    <!DOCTYPE html>
    <html><head><title>Cancel Subscription - ShadowStrike Options</title></head>
    <body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; padding: 50px;">
    <div style="max-width: 600px; margin: 0 auto; background: rgba(6, 95, 70, 0.3); padding: 40px; border-radius: 15px; text-align: center;">
        <h1 style="color: #ef4444;">😔 We're Sorry to See You Go</h1>
        <p style="margin: 20px 0;">Are you sure you want to cancel your ShadowStrike Options subscription?</p>
        
        <div style="background: rgba(239, 68, 68, 0.2); padding: 20px; border-radius: 10px; margin: 30px 0;">
            <h3 style="color: #ef4444;">You'll lose access to:</h3>
            <ul style="color: #a7f3d0; text-align: left; display: inline-block;">
                <li>Real-time options analysis</li>
                <li>Daily trading alerts</li>
                <li>Portfolio tracking</li>
                <li>Mobile app access</li>
                <li>Options scanner</li>
            </ul>
        </div>
        
        <form method="POST" style="display: inline-block; margin-right: 10px;">
            <button type="submit" style="background: #ef4444; color: white; padding: 12px 25px; border: none; border-radius: 8px; font-weight: bold; cursor: pointer;">
                Yes, Cancel Subscription
            </button>
        </form>
        
        <a href="/billing" style="background: #10b981; color: white; padding: 12px 25px; text-decoration: none; border-radius: 8px; font-weight: bold;">
            Keep Subscription
        </a>
    </div>
    </body></html>
    """

# Update existing dashboard route to include trial warning
@app.route('/dashboard')
@subscription_required  # This will redirect expired users to subscribe
def dashboard():
    if 'user_id' not in session:
        flash('Please login to access the dashboard', 'error')
        return redirect(url_for('login'))
    
    try:
        user = User.query.get(session['user_id'])
        if not user:
            session.clear()
            flash('User not found. Please login again.', 'error')
            return redirect(url_for('login'))
        
        # Show trial warning if less than 7 days left
        if user.subscription_status == 'trial' and user.days_left_in_trial() <= 7:
            flash(f'Your trial expires in {user.days_left_in_trial()} days. Subscribe now to keep your access!', 'warning')
        
        # Get market data
        market_status = get_market_status()
        top_movers = get_top_movers()
        
        # Get user's trades with real P&L
        trades = Trade.query.filter_by(user_id=user.id).all()
        
        # Calculate portfolio stats with real prices
        total_pnl = 0
        open_trades = 0
        enhanced_trades = []
        
        for trade in trades:
            if trade.status == 'open':
                open_trades += 1
                # Get current stock price
                stock_data = get_stock_price(trade.symbol)
                current_stock_price = stock_data['price']
                
                # Calculate option probability
                days_to_expiry = 30  # Assume 30 days for demo
                probability = calculate_option_probability(
                    current_stock_price, trade.strike_price, days_to_expiry, trade.option_type
                )
                
                # Estimate current option price (simplified)
                if trade.option_type == 'CALL':
                    intrinsic_value = max(0, current_stock_price - trade.strike_price)
                else:
                    intrinsic_value = max(0, trade.strike_price - current_stock_price)
                
                time_value = trade.entry_price * 0.3  # Assume 30% time value remaining
                current_option_price = intrinsic_value + time_value
                
                pnl = (current_option_price - trade.entry_price) * trade.quantity * 100
                total_pnl += pnl
                
                enhanced_trades.append({
                    'trade': trade,
                    'current_stock_price': current_stock_price,
                    'current_option_price': round(current_option_price, 2),
                    'pnl': round(pnl, 2),
                    'probability': probability
                })
        
        try:
            return render_template('dashboard.html', 
                                 user=user, 
                                 trades=enhanced_trades, 
                                 total_pnl=total_pnl,
                                 open_trades=open_trades,
                                 market_status=market_status,
                                 top_movers=top_movers)
        except Exception as e:
            logger.error(f"Error rendering dashboard.html: {e}")
            return f"""
            <!DOCTYPE html>
            <html><head><title>Dashboard - ShadowStrike Options</title></head>
            <body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; padding: 50px;">
            <h1 style="color: #10b981;">🎯 ShadowStrike Options - Dashboard</h1>
            <p>Welcome {user.username}! ({user.subscription_status} - {user.days_left_in_trial() if user.subscription_status == 'trial' else 'Active'})</p>
            <p>Market Status: {market_status['status']}</p>
            <p>Portfolio P&L: ${total_pnl:.2f}</p>
            <p>Open Trades: {open_trades}</p>
            
            {'<div style="background: rgba(239, 68, 68, 0.2); padding: 15px; border-radius: 10px; margin: 20px 0;"><strong>⏰ Trial expires in ' + str(user.days_left_in_trial()) + ' days!</strong> <a href="/subscribe" style="color: #10b981;">Subscribe now</a></div>' if user.subscription_status == 'trial' and user.days_left_in_trial() <= 7 else ''}
            
            <h3>Top Market Movers:</h3>
            {''.join([f"<p>{mover['symbol']}: ${mover['price']} ({mover['change_percent']:+.2f}%)</p>" for mover in top_movers])}
            
            <p><a href="/logout" style="color: #ef4444;">Logout</a> | 
            <a href="/billing" style="color: #10b981;">Billing</a> | 
            <a href="/email-settings" style="color: #10b981;">Email Settings</a> | 
            <a href="/market-data" style="color: #10b981;">Market Data</a></p>
            </body></html>
            """
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return redirect(url_for('login'))
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
