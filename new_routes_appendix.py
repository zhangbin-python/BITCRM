
# ============================================================================
# TASKS API - Task Status Toggle
# ============================================================================

@api_bp.route('/tasks/<int:task_id>/toggle-status', methods=['POST'])
@login_required
def toggle_task_status(task_id):
    """Toggle task status between In Progress and Completed."""
    task = Task.query.get_or_404(task_id)
    
    # Check if user has permission to modify this task
    if not current_user.is_admin() and task.owner_id != current_user.id:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    
    try:
        data = request.get_json() or {}
        new_status = data.get('new_status')
        
        # Determine new status
        if new_status:
            task.status = new_status
        else:
            # Toggle between In Progress and Completed
            if task.status == 'In Progress':
                task.status = 'Completed'
                # Log task completion
                log_task_completed(current_user, task, request.remote_addr)
            elif task.status == 'Completed':
                task.status = 'In Progress'
                # Log task reopening
                log_task_reopened(current_user, task, request.remote_addr)
            elif task.status == 'Overdue':
                # Can't toggle from Overdue directly, must go to Completed
                task.status = 'Completed'
                log_task_completed(current_user, task, request.remote_addr)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Task status updated successfully',
            'new_status': task.status
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# DASHBOARD API - Pipeline Data for Kanban Board
# ============================================================================

@api_bp.route('/dashboard/pipeline-kanban', methods=['GET'])
@login_required
def get_pipeline_kanban_data():
    """Get pipeline data for the Kanban board visualization."""
    
    # Get filter parameters
    show_lost = request.args.get('show_lost', 'false') == 'true'
    
    # Build base query
    query = Pipeline.query
    
    # Filter by access permissions
    if not current_user.is_admin():
        query = query.filter(
            or_(Pipeline.owner_id == current_user.id,
                Pipeline.owner_id.in_([u.id for u in current_user.supported_pipelines]))
        )
    
    # Filter by lost status
    if not show_lost:
        query = query.filter(Pipeline.stage != '6b) Deal Lost')
    
    # Get all active deals
    pipelines = query.order_by(Pipeline.date_added.desc()).all()
    
    # Define pipeline stages for kanban board
    stages = [
        {'value': 'Prospecting', 'label': '1) Prospecting'},
        {'value': 'Qualification', 'label': '2) Qualification'},
        {'value': 'Needs Analysis', 'label': '3) Needs Analysis'},
        {'value': 'Value Proposition', 'label': '4) Value Proposition'},
        {'value': 'Proposal', 'label': '5) Proposal'},
        {'value': 'Negotiation', 'label': '6) Negotiation'},
        {'value': '6a) Deal Won', 'label': '6a) Deal Won'},
        {'value': '7) Activated', 'label': '7) Activated'},
    ]
    
    # Serialize deals data
    deals_data = []
    for p in pipelines:
        # Get latest follow-up date
        latest_followup = None
        if p.follow_up:
            # Parse follow-up dates from the text
            import re
            date_pattern = r'(\d{4}-\d{2}-\d{2})'
            dates = re.findall(date_pattern, p.follow_up)
            if dates:
                latest_followup = max(dates)
        
        deal = {
            'id': p.id,
            'company': p.company,
            'name': p.name,
            'owner_name': p.owner.username if p.owner else None,
            'tcv_usd': p.tcv_usd,
            'mrc_usd': p.mrc_usd,
            'win_rate': p.win_rate,
            'stage': p.stage,
            'est_sign_date': p.est_sign_date.strftime('%Y-%m-%d') if p.est_sign_date else None,
            'latest_followup': latest_followup,
            'level': p.level
        }
        deals_data.append(deal)
    
    return jsonify({
        'stages': stages,
        'deals': deals_data
    })

@api_bp.route('/dashboard/owner-metrics', methods=['GET'])
@login_required
def get_owner_metrics_data():
    """Get per-owner breakdown metrics for dashboard filtering."""
    
    # Get all active users
    users = User.query.filter_by(is_active=True).all()
    
    # Build base pipeline query
    base_pipeline_query = Pipeline.query
    if not current_user.is_admin():
        base_pipeline_query = base_pipeline_query.filter(
            or_(Pipeline.owner_id == current_user.id,
                Pipeline.owner_id.in_([u.id for u in current_user.supported_pipelines]))
        )
    
    # Get metrics for each user
    metrics = []
    for user in users:
        # Count leads for this user
        leads_count = SalesLead.query.filter_by(owner_id=user.id).count()
        qualified_count = SalesLead.query.filter_by(owner_id=user.id, leads_status='Qualified').count()
        
        # Count pipeline deals for this user
        pipeline_deals = base_pipeline_query.filter(Pipeline.owner_id == user.id).all()
        pipeline_count = len(pipeline_deals)
        tcv = sum(p.tcv_usd for p in pipeline_deals)
        
        # Count customers (companies in pipeline)
        customer_count = len(set(p.company for p in pipeline_deals if p.company))
        
        metrics.append({
            'user_id': user.id,
            'username': user.username,
            'role': user.role,
            'leads_count': leads_count,
            'qualified_count': qualified_count,
            'pipeline_count': pipeline_count,
            'customer_count': customer_count,
            'tcv': tcv
        })
    
    return jsonify({'metrics': metrics})
