"""Payment routes for Stripe and Paystack"""

import os
import stripe
import requests
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, PaymentPlan, Subscription

payments_bp = Blueprint('payments', __name__)

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY')


def get_plan_by_stripe_price(price_id):
    return PaymentPlan.query.filter_by(stripe_price_id=price_id).first()


def get_plan_by_paystack_code(plan_code):
    return PaymentPlan.query.filter_by(paystack_plan_code=plan_code).first()


@payments_bp.route('/subscribe/stripe/<plan_code>')
@login_required
def stripe_checkout(plan_code):
    plan = PaymentPlan.query.filter_by(code=plan_code).first()
    if not plan or not plan.stripe_price_id:
        flash('Invalid plan selected.', 'error')
        return redirect(url_for('public.pricing'))
    
    if not stripe.api_key:
        flash('Stripe is not configured. Please contact support.', 'error')
        return redirect(url_for('public.pricing'))
    
    try:
        domain = os.environ.get('REPLIT_DEV_DOMAIN', request.host_url.rstrip('/'))
        if not domain.startswith('http'):
            domain = f'https://{domain}'
        
        checkout_session = stripe.checkout.Session.create(
            customer_email=current_user.email,
            payment_method_types=['card'],
            line_items=[{
                'price': plan.stripe_price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=f'{domain}/payment/success?session_id={{CHECKOUT_SESSION_ID}}',
            cancel_url=f'{domain}/pricing',
            metadata={
                'user_id': str(current_user.id),
                'plan_code': plan.code
            }
        )
        return redirect(checkout_session.url)
    except stripe.error.StripeError as e:
        flash(f'Payment error: {str(e)}', 'error')
        return redirect(url_for('public.pricing'))


@payments_bp.route('/subscribe/paystack/<plan_code>')
@login_required
def paystack_checkout(plan_code):
    plan = PaymentPlan.query.filter_by(code=plan_code).first()
    if not plan or not plan.paystack_plan_code:
        flash('Invalid plan selected.', 'error')
        return redirect(url_for('public.pricing'))
    
    if not PAYSTACK_SECRET_KEY:
        flash('Paystack is not configured. Please contact support.', 'error')
        return redirect(url_for('public.pricing'))
    
    try:
        domain = os.environ.get('REPLIT_DEV_DOMAIN', request.host_url.rstrip('/'))
        if not domain.startswith('http'):
            domain = f'https://{domain}'
        
        headers = {
            'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'email': current_user.email,
            'plan': plan.paystack_plan_code,
            'callback_url': f'{domain}/payment/paystack/callback',
            'metadata': {
                'user_id': str(current_user.id),
                'plan_code': plan.code
            }
        }
        
        response = requests.post(
            'https://api.paystack.co/transaction/initialize',
            headers=headers,
            json=data
        )
        
        result = response.json()
        if result.get('status'):
            return redirect(result['data']['authorization_url'])
        else:
            flash('Could not initialize payment. Please try again.', 'error')
            return redirect(url_for('public.pricing'))
            
    except Exception as e:
        flash(f'Payment error: {str(e)}', 'error')
        return redirect(url_for('public.pricing'))


@payments_bp.route('/payment/success')
@login_required
def payment_success():
    session_id = request.args.get('session_id')
    
    if not session_id:
        flash('Invalid payment session.', 'error')
        return redirect(url_for('subscriber.dashboard'))
    
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        
        if session.payment_status == 'paid':
            existing_sub = Subscription.query.filter_by(
                provider_subscription_id=session.subscription
            ).first()
            
            if not existing_sub:
                stripe_sub = stripe.Subscription.retrieve(session.subscription)
                plan_code = session.metadata.get('plan_code')
                
                subscription = Subscription(
                    user_id=current_user.id,
                    provider='stripe',
                    provider_subscription_id=session.subscription,
                    plan_code=plan_code,
                    status='active',
                    current_period_end=datetime.fromtimestamp(stripe_sub.current_period_end)
                )
                db.session.add(subscription)
                db.session.commit()
            
            flash('Subscription activated successfully!', 'success')
        else:
            flash('Payment was not completed.', 'warning')
            
    except stripe.error.StripeError as e:
        flash(f'Error verifying payment: {str(e)}', 'error')
    
    return redirect(url_for('subscriber.dashboard'))


@payments_bp.route('/payment/paystack/callback')
@login_required
def paystack_callback():
    reference = request.args.get('reference')
    
    if not reference:
        flash('Invalid payment reference.', 'error')
        return redirect(url_for('subscriber.dashboard'))
    
    try:
        headers = {
            'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}'
        }
        
        response = requests.get(
            f'https://api.paystack.co/transaction/verify/{reference}',
            headers=headers
        )
        
        result = response.json()
        
        if result.get('status') and result['data']['status'] == 'success':
            metadata = result['data'].get('metadata', {})
            plan_code = metadata.get('plan_code')
            
            existing_sub = Subscription.query.filter_by(
                provider_subscription_id=reference
            ).first()
            
            if not existing_sub:
                subscription = Subscription(
                    user_id=current_user.id,
                    provider='paystack',
                    provider_subscription_id=reference,
                    plan_code=plan_code,
                    status='active',
                    current_period_end=datetime.utcnow() + timedelta(days=30)
                )
                db.session.add(subscription)
                db.session.commit()
            
            flash('Subscription activated successfully!', 'success')
        else:
            flash('Payment verification failed.', 'error')
            
    except Exception as e:
        flash(f'Error verifying payment: {str(e)}', 'error')
    
    return redirect(url_for('subscriber.dashboard'))


@payments_bp.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    try:
        if endpoint_secret:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        else:
            event = stripe.Event.construct_from(request.get_json(), stripe.api_key)
        
        if event['type'] == 'customer.subscription.updated':
            subscription_data = event['data']['object']
            sub = Subscription.query.filter_by(
                provider_subscription_id=subscription_data['id']
            ).first()
            
            if sub:
                sub.status = subscription_data['status']
                sub.current_period_end = datetime.fromtimestamp(
                    subscription_data['current_period_end']
                )
                db.session.commit()
        
        elif event['type'] == 'customer.subscription.deleted':
            subscription_data = event['data']['object']
            sub = Subscription.query.filter_by(
                provider_subscription_id=subscription_data['id']
            ).first()
            
            if sub:
                sub.status = 'cancelled'
                db.session.commit()
        
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@payments_bp.route('/webhook/paystack', methods=['POST'])
def paystack_webhook():
    try:
        data = request.get_json()
        event = data.get('event')
        
        if event == 'subscription.disable':
            subscription_code = data['data']['subscription_code']
            sub = Subscription.query.filter_by(
                provider_subscription_id=subscription_code
            ).first()
            
            if sub:
                sub.status = 'cancelled'
                db.session.commit()
        
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400
