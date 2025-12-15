"""Payment routes for Stripe and Paystack"""

import os
import stripe
import requests
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, PaymentPlan, Subscription, LicensedPack, License, Payment, NIGERIA_REGIONS

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
    
    if not endpoint_secret:
        return jsonify({'error': 'Webhook secret not configured'}), 500
    
    if not sig_header:
        return jsonify({'error': 'Missing signature'}), 400
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        
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
    import hashlib
    import hmac
    
    paystack_secret = os.environ.get('PAYSTACK_SECRET_KEY')
    if not paystack_secret:
        return jsonify({'error': 'Paystack secret not configured'}), 500
    
    signature = request.headers.get('X-Paystack-Signature')
    if not signature:
        return jsonify({'error': 'Missing signature'}), 400
    
    payload = request.get_data()
    computed_signature = hmac.new(
        paystack_secret.encode('utf-8'),
        payload,
        hashlib.sha512
    ).hexdigest()
    
    if not hmac.compare_digest(signature, computed_signature):
        return jsonify({'error': 'Invalid signature'}), 400
    
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


@payments_bp.route('/pack/<pack_code>/<provider>')
@login_required
def pack_checkout(pack_code, provider):
    """Initiate one-time payment for a licensed data pack."""
    pack = LicensedPack.query.filter_by(code=pack_code, active=True).first()
    if not pack:
        flash('Invalid data pack selected.', 'error')
        return redirect(url_for('subscriber.packs'))
    
    current_month = datetime.utcnow().strftime('%Y-%m')
    
    return render_template('pack_checkout.html',
                           pack=pack,
                           provider=provider,
                           current_month=current_month,
                           regions=NIGERIA_REGIONS)


@payments_bp.route('/pack/<pack_code>/<provider>/process', methods=['POST'])
@login_required
def process_pack_payment(pack_code, provider):
    """Process one-time payment for a licensed data pack."""
    pack = LicensedPack.query.filter_by(code=pack_code, active=True).first()
    if not pack:
        flash('Invalid data pack selected.', 'error')
        return redirect(url_for('subscriber.packs'))
    
    regions = request.form.getlist('regions')
    crops_text = request.form.get('crops', '')
    crops = [c.strip() for c in crops_text.split(',') if c.strip()]
    
    if len(regions) == 0:
        flash('Please select at least one region.', 'error')
        return redirect(url_for('payments.pack_checkout', pack_code=pack_code, provider=provider))
    
    if len(regions) > pack.regions_allowed:
        flash(f'You can select up to {pack.regions_allowed} region(s) with this pack.', 'error')
        return redirect(url_for('payments.pack_checkout', pack_code=pack_code, provider=provider))
    
    if pack.crops_allowed and len(crops) > pack.crops_allowed:
        flash(f'You can specify up to {pack.crops_allowed} crop(s) with this pack.', 'error')
        return redirect(url_for('payments.pack_checkout', pack_code=pack_code, provider=provider))
    
    current_month = datetime.utcnow().strftime('%Y-%m')
    
    domain = os.environ.get('REPLIT_DEV_DOMAIN', request.host_url.rstrip('/'))
    if not domain.startswith('http'):
        domain = f'https://{domain}'
    
    if provider == 'stripe':
        if not stripe.api_key:
            flash('Stripe is not configured. Please contact support.', 'error')
            return redirect(url_for('subscriber.packs'))
        
        try:
            checkout_session = stripe.checkout.Session.create(
                customer_email=current_user.email,
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'unit_amount': pack.price_usd * 100,
                        'product_data': {
                            'name': pack.name,
                            'description': f'{pack.description} - {current_month} Snapshot',
                        },
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=f'{domain}/payment/pack/success?session_id={{CHECKOUT_SESSION_ID}}',
                cancel_url=f'{domain}/packs',
                metadata={
                    'user_id': str(current_user.id),
                    'pack_code': pack.code,
                    'regions': ','.join(regions),
                    'crops': ','.join(crops),
                    'snapshot_month': current_month,
                    'payment_type': 'licensed_pack'
                }
            )
            return redirect(checkout_session.url)
        except stripe.error.StripeError as e:
            flash(f'Payment error: {str(e)}', 'error')
            return redirect(url_for('subscriber.packs'))
    
    elif provider == 'paystack':
        if not PAYSTACK_SECRET_KEY:
            flash('Paystack is not configured. Please contact support.', 'error')
            return redirect(url_for('subscriber.packs'))
        
        try:
            headers = {
                'Authorization': f'Bearer {PAYSTACK_SECRET_KEY}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'email': current_user.email,
                'amount': pack.price_ngn * 100,
                'currency': 'NGN',
                'callback_url': f'{domain}/payment/pack/paystack/callback',
                'metadata': {
                    'user_id': str(current_user.id),
                    'pack_code': pack.code,
                    'regions': ','.join(regions),
                    'crops': ','.join(crops),
                    'snapshot_month': current_month,
                    'payment_type': 'licensed_pack'
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
                return redirect(url_for('subscriber.packs'))
                
        except Exception as e:
            flash(f'Payment error: {str(e)}', 'error')
            return redirect(url_for('subscriber.packs'))
    
    flash('Invalid payment provider.', 'error')
    return redirect(url_for('subscriber.packs'))


@payments_bp.route('/payment/pack/success')
@login_required
def pack_payment_success():
    """Handle successful Stripe payment for a licensed pack."""
    session_id = request.args.get('session_id')
    
    if not session_id:
        flash('Invalid payment session.', 'error')
        return redirect(url_for('subscriber.licenses'))
    
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        
        if session.payment_status == 'paid':
            existing_license = License.query.filter_by(
                stripe_payment_intent_id=session.payment_intent
            ).first()
            
            if not existing_license:
                metadata = session.metadata
                pack = LicensedPack.query.filter_by(code=metadata.get('pack_code')).first()
                
                if pack:
                    regions = metadata.get('regions', '').split(',') if metadata.get('regions') else []
                    crops = metadata.get('crops', '').split(',') if metadata.get('crops') else []
                    
                    license_record = License(
                        user_id=current_user.id,
                        licensed_pack_id=pack.id,
                        regions_selected=regions,
                        crops_selected=crops,
                        snapshot_month=metadata.get('snapshot_month'),
                        status='active',
                        stripe_payment_intent_id=session.payment_intent
                    )
                    db.session.add(license_record)
                    
                    payment_record = Payment(
                        user_id=current_user.id,
                        provider='stripe',
                        provider_reference=session.payment_intent,
                        payment_type='licensed_pack',
                        amount_usd=pack.price_usd,
                        status='completed',
                        metadata_json={
                            'pack_code': pack.code,
                            'regions': regions,
                            'crops': crops,
                            'snapshot_month': metadata.get('snapshot_month')
                        }
                    )
                    db.session.add(payment_record)
                    db.session.commit()
            
            flash('Your data pack license has been activated!', 'success')
        else:
            flash('Payment was not completed.', 'warning')
            
    except stripe.error.StripeError as e:
        flash(f'Error verifying payment: {str(e)}', 'error')
    
    return redirect(url_for('subscriber.licenses'))


@payments_bp.route('/payment/pack/paystack/callback')
@login_required
def pack_paystack_callback():
    """Handle successful Paystack payment for a licensed pack."""
    reference = request.args.get('reference')
    
    if not reference:
        flash('Invalid payment reference.', 'error')
        return redirect(url_for('subscriber.licenses'))
    
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
            existing_license = License.query.filter_by(
                paystack_reference=reference
            ).first()
            
            if not existing_license:
                metadata = result['data'].get('metadata', {})
                pack = LicensedPack.query.filter_by(code=metadata.get('pack_code')).first()
                
                if pack:
                    regions = metadata.get('regions', '').split(',') if metadata.get('regions') else []
                    crops = metadata.get('crops', '').split(',') if metadata.get('crops') else []
                    
                    license_record = License(
                        user_id=current_user.id,
                        licensed_pack_id=pack.id,
                        regions_selected=regions,
                        crops_selected=crops,
                        snapshot_month=metadata.get('snapshot_month'),
                        status='active',
                        paystack_reference=reference
                    )
                    db.session.add(license_record)
                    
                    payment_record = Payment(
                        user_id=current_user.id,
                        provider='paystack',
                        provider_reference=reference,
                        payment_type='licensed_pack',
                        amount_ngn=pack.price_ngn,
                        status='completed',
                        metadata_json={
                            'pack_code': pack.code,
                            'regions': regions,
                            'crops': crops,
                            'snapshot_month': metadata.get('snapshot_month')
                        }
                    )
                    db.session.add(payment_record)
                    db.session.commit()
            
            flash('Your data pack license has been activated!', 'success')
        else:
            flash('Payment verification failed.', 'error')
            
    except Exception as e:
        flash(f'Error verifying payment: {str(e)}', 'error')
    
    return redirect(url_for('subscriber.licenses'))
