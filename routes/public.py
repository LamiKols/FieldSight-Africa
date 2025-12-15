"""Public routes"""

from flask import Blueprint, render_template
from models import PaymentPlan, Dataset, DatasetMonth

public_bp = Blueprint('public', __name__)


@public_bp.route('/')
def home():
    return render_template('home.html')


@public_bp.route('/pricing')
def pricing():
    plans = PaymentPlan.query.all()
    return render_template('pricing.html', plans=plans)
