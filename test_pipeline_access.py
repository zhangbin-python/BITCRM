import sys
sys.path.insert(0, '.')
from app import create_app
from models import db, User, Pipeline

app = create_app()
with app.app_context():
    # Get Cean
    cean = User.query.filter_by(username='Cean').first()
    print(f'Cean: {cean.username}, role={cean.role}, is_admin={cean.is_admin()}')
    print()

    # Get Cean's supported_pipelines
    print('Cean.supported_pipelines:')
    for p in cean.supported_pipelines:
        print(f'  - ID={p.id}: {p.name}, owner_id={p.owner_id}')
    print()

    # Get Cean's supported_pipeline IDs
    supported_ids = [u.id for u in cean.supported_pipelines]
    print(f'IDs from supported_pipelines: {supported_ids}')
    print()

    # What the query is trying to do
    print('Query that should be executed:')
    print('Pipeline.owner_id.in_(', supported_ids, ')')
    print()

    # What Pipelines would match this query
    matching_pipelines = Pipeline.query.filter(
        Pipeline.owner_id.in_(supported_ids)
    ).all()
    print(f'Pipelines matching owner_id.in_(supported_ids): {len(matching_pipelines)}')
    for p in matching_pipelines:
        print(f'  - ID={p.id}: {p.name}, owner_id={p.owner_id}')
    print()

    # What if Cean.is_admin() returns True incorrectly?
    print(f'If is_admin() were True, Cean would see ALL pipelines')
    all_pipelines = Pipeline.query.all()
    print(f'Total pipelines in DB: {len(all_pipelines)}')
