@projects.route('/projects/create', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'cs')
def create():
    scopes = Scope.query.filter_by(active=True).order_by(Scope.name).all()
    cs_users = User.query.filter(
        User.role.in_(['cs', 'admin'])
    ).order_by(User.name).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        cs_lead_id = request.form.get('cs_lead_id')
        client = request.form.get('client', '').strip()
        scope_id = request.form.get('scope_id')
        design_teams = request.form.getlist('design_teams') 
        importance = request.form.get('importance')
        design_needed_by = request.form.get('design_needed_by')
        execution_date = request.form.get('execution_date')
        job_number = request.form.get('job_number', '').strip()
        value = request.form.get('value')
        conditional_reviewers = User.query.filter_by(is_conditional_reviewer=True).all()
        

        errors = []

        if not name:
            errors.append("Project name is required.")
        if not cs_lead_id:
            errors.append("Client Servicing Lead is required.")
        if not client:
            errors.append("Client name is required.")    
        if not scope_id:
            errors.append("Project scope is required.")
        if not design_teams:    
            errors.append("At least one design team must be selected.")
        if not importance:
            errors.append("Importance level is required.")
        if not design_needed_by:
            errors.append("Design needed by date is required.")
        if not execution_date:        
            errors.append("Execution date is required.")
        if not job_number:
            errors.append("Job number is required.")
        if not value:
            errors.append("Project value is required.")
        

        if job_number:
            existing = Project.query.filter_by(job_number=job_number).first()
            if existing:
                errors.append("Job number must be unique. A project with this job number already exists.")
        

        brief_file = None
        file = request.files.get('brief_file')
        if not file or file.filename == '':
            errors.append("Project brief file is required.")
        else:
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))
            brief_file = unique_filename
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('projects/create.html', scopes=scopes, cs_users=cs_users, conditional_reviewers=conditional_reviewers)
        
        project = Project(
            name=name,
            cs_lead_id=int(cs_lead_id),
            client=client,
            scope_id=int(scope_id),
            design_teams_requested=','.join(design_teams),
            importance=importance,
            design_needed_by=date.fromisoformat(design_needed_by),
            execution_date=date.fromisoformat(execution_date),
            job_number=job_number,
            value=float(value),
            brief_file=brief_file,
            created_by_id=current_user.id
        )
        db.session.add(project)
        db.session.commit()

        notify_team_leads_of_new_project(
        project=project,
        teams_requested=design_teams,
        triggered_by=current_user
        )

        flash(f'Project "{name}" created successfully.', 'success')
        return redirect(url_for('main.index'))

    return render_template('projects/create.html',
                           scopes=scopes, cs_users=cs_users)