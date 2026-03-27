import os

from app import create_app


def _get_bool_env(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


app = create_app()


# Only run Flask dev server when executed directly.
# Gunicorn imports this module but doesn't execute this block.
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = _get_bool_env(
        'BITCRM_DEBUG',
        _get_bool_env('FLASK_DEBUG', os.environ.get('FLASK_ENV') == 'development'),
    )
    app.run(host='0.0.0.0', port=port, debug=debug, use_reloader=debug)
