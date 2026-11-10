"""Compatibility redirects for the retired identity-switching college demo."""
from flask import Blueprint, jsonify, redirect

college = Blueprint('college', __name__)


@college.get('/college/demo')
@college.get('/college/demo/')
@college.get('/college/professor')
@college.get('/college/demo/professor')
def retired_dashboard():
    return redirect('/college', code=302)


@college.route('/api/college/<path:legacy_path>', methods=['GET', 'POST'])
def retired_api(legacy_path):
    return jsonify(error='The identity-switching demo has been retired. Sign in to the unified college portal.',
                   portal='/college', policy='/api/portal/policy'), 410
