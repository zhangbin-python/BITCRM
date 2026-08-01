import os
import tempfile
import unittest
from datetime import date, datetime

from app import create_app
from extensions import db
from sqlalchemy import text
from models import ActivityLog, DeletedRecord, Pipeline, SalesActivity, SalesLead, Task, User
from schema_updates import ensure_sales_activity_columns, ensure_sales_activity_statuses, ensure_sales_activity_terminology


class SalesActivitiesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, 'test_bitcrm.db')

        class TestConfig:
            TESTING = True
            SECRET_KEY = 'test-secret'
            SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path}'
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            SQLALCHEMY_ENGINE_OPTIONS = {}
            CACHE_TYPE = 'SimpleCache'
            UPLOAD_FOLDER = os.path.join(self.temp_dir.name, 'uploads')
            EXCEL_TEMPLATES_FOLDER = os.path.join(self.temp_dir.name, 'templates')

        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()

        admin = User(username='Admin', role='admin')
        admin.set_password('bitcrm')
        db.session.add(admin)
        db.session.commit()
        self.admin_id = admin.id

        self.client = self.app.test_client()
        response = self.client.post(
            '/login', data={'username': 'Admin', 'password': 'bitcrm'},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()
        self.temp_dir.cleanup()

    def _lead(self, company='Activity Test Co', status='Unqualified', requirements='Cloud service'):
        lead = SalesLead(
            name='Test Contact', company=company, owner_id=self.admin_id,
            leads_status=status, requirements=requirements,
        )
        db.session.add(lead)
        db.session.commit()
        return lead

    def test_followup_and_todo_create_two_independent_remote_engagement_activities(self):
        lead = self._lead()
        response = self.client.post(
            f'/leads/{lead.id}/add-followup',
            data={
                'followup_text': 'Customer confirmed the technical scope.',
                'todo_text': 'Send the revised quotation.',
                'todo_due_date': '2026-08-05',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])

        activities = SalesActivity.query.order_by(SalesActivity.id).all()
        self.assertEqual(len(activities), 2)
        completed, pending = activities
        self.assertEqual((completed.activity_type, completed.remote_engagement_subtype, completed.status),
                         ('Remote Engagement', 'Follow-up', 'Completed'))
        self.assertEqual(completed.completion_notes, 'Customer confirmed the technical scope.')
        self.assertEqual((pending.activity_type, pending.remote_engagement_subtype, pending.status),
                         ('Remote Engagement', 'Next Steps / To-do', 'Scheduled'))
        self.assertEqual(pending.followup_notes, 'Send the revised quotation.')

        task = Task.query.one()
        self.assertEqual(task.sales_activity_id, pending.id)
        self.assertEqual(task.due_date, date(2026, 8, 5))
        self.assertIn('Customer confirmed the technical scope.', lead.follow_up)
        self.assertIn('Send the revised quotation.', lead.follow_up)

    def test_task_requires_feedback_and_preserves_original_next_steps(self):
        lead = self._lead()
        self.client.post(
            f'/leads/{lead.id}/add-followup',
            data={'todo_text': 'Arrange solution workshop.', 'todo_due_date': '2026-08-06'},
        )
        task = Task.query.one()
        activity = SalesActivity.query.one()

        response = self.client.post(f'/tasks/{task.id}/complete', data={}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        db.session.refresh(task)
        self.assertNotEqual(task.status, 'Completed')

        response = self.client.post(
            f'/tasks/{task.id}/complete',
            data={'completion_notes': 'Workshop completed; technical team approved the design.'},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        db.session.refresh(task)
        db.session.refresh(activity)
        self.assertEqual(task.status, 'Completed')
        self.assertEqual(activity.status, 'Completed')
        self.assertEqual(activity.followup_notes, 'Arrange solution workshop.')
        self.assertEqual(activity.completion_notes, 'Workshop completed; technical team approved the design.')

    def test_on_site_visit_supports_cross_date_schedule_and_feedback_sync(self):
        lead = self._lead()
        response = self.client.post(
            '/sales-activities/add',
            data={
                'activity_type': 'On-site Visit',
                'source_type': 'Sales Leads',
                'sales_lead_id': str(lead.id),
                'company': lead.company,
                'activity_date': '2026-07-30',
                'start_date': '2026-07-30',
                'start_time': '23:00',
                'end_date': '2026-07-31',
                'end_time': '01:00',
                'owner_id': str(self.admin_id),
                'address': '88 Customer Road',
                'contact_name[]': ['Alice', 'Bob'],
                'contact_position[]': ['CTO', 'Engineer'],
                'contact_information[]': ['alice@example.com', '+1 555 0100'],
                'purpose_project': 'Data center visit',
                'expected_result': 'Confirm migration window',
                'remarks': 'Bring technical diagram',
            },
        )
        self.assertEqual(response.status_code, 302)
        activity = SalesActivity.query.one()
        task = Task.query.one()
        self.assertEqual(activity.estimated_start_at.strftime('%Y-%m-%d %H:%M'), '2026-07-30 23:00')
        self.assertEqual(activity.estimated_end_at.strftime('%Y-%m-%d %H:%M'), '2026-07-31 01:00')
        self.assertEqual(len(activity.contacts), 2)
        self.assertEqual(task.sales_activity_id, activity.id)
        self.assertIn('On-site Visit scheduled', lead.follow_up)

        response = self.client.post(
            f'/sales-activities/{activity.id}/followup',
            data={
                'completion_notes': 'Customer approved the migration window.',
                'todo_text': 'Send final migration plan.',
                'todo_due_date': '2026-08-10',
            },
        )
        self.assertEqual(response.status_code, 302)
        db.session.refresh(activity)
        db.session.refresh(task)
        self.assertEqual(activity.status, 'Completed')
        self.assertEqual(task.status, 'Completed')
        self.assertIn('On-site Visit feedback: Customer approved', lead.follow_up)
        self.assertIn('Send final migration plan.', lead.follow_up)
        self.assertEqual(SalesActivity.query.count(), 2)
        next_step_activity = SalesActivity.query.filter_by(remote_engagement_subtype='Next Steps / To-do').one()
        self.assertEqual(next_step_activity.status, 'Scheduled')
        self.assertEqual(Task.query.count(), 2)

    def test_invalid_on_site_visit_reopens_form_and_uses_start_date_as_activity_date(self):
        lead = self._lead(company='Retained Visit Form Co')
        data = {
            'activity_type': 'On-site Visit',
            'source_type': 'Sales Leads',
            'sales_lead_id': str(lead.id),
            'company': lead.company,
            'start_date': '2026-08-12',
            'start_time': '15:00',
            'end_date': '2026-08-12',
            'end_time': '14:00',
            'owner_id': str(self.admin_id),
            'address': 'Retained address',
            'contact_name[]': ['Retained Contact', 'Second Contact'],
            'contact_position[]': ['Director', 'Assistant'],
            'contact_information[]': ['retained@example.com', '+1 555 0199'],
            'purpose_project': 'Retained purpose',
            'expected_result': 'Retained expected result',
            'remarks': 'Retained remarks',
        }
        response = self.client.post('/sales-activities/add', data=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SalesActivity.query.count(), 0)
        self.assertIn(b'Estimated End Time must be later than Estimated Start Time.', response.data)
        self.assertIn(b'id="addSalesActivityModal"', response.data)
        self.assertIn(b'getOrCreateInstance(modalElement).show()', response.data)
        self.assertIn(b'value="2026-08-12"', response.data)
        self.assertIn(b'value="15:00"', response.data)
        self.assertIn(b'value="14:00"', response.data)
        self.assertIn(b'Retained address', response.data)
        self.assertIn(b'Retained Contact', response.data)
        self.assertIn(b'Second Contact', response.data)

        data['end_time'] = '16:00'
        response = self.client.post('/sales-activities/add', data=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        activity = SalesActivity.query.one()
        self.assertEqual(activity.activity_date.isoformat(), '2026-08-12')
        self.assertEqual(activity.estimated_start_at.strftime('%H:%M'), '15:00')
        self.assertEqual(activity.estimated_end_at.strftime('%H:%M'), '16:00')

    def test_add_sales_activity_defaults_to_on_site_visit(self):
        response = self.client.get('/sales-activities/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<option value="On-site Visit" selected>', response.data)
        self.assertIn(b'<th>Date</th>', response.data)
        self.assertIn(b'min-width: 1900px', response.data)
        self.assertIn(b'sales-activity-table-wrapper', response.data)
        self.assertNotIn(b'<th>Remote Engagement Subtype</th>', response.data)

    def test_strict_sources_reject_manual_company_but_other_source_accepts_it(self):
        response = self.client.post(
            '/sales-activities/add',
            data={
                'activity_type': 'Remote Engagement', 'source_type': 'Sales Leads',
                'company': 'Typed Company', 'activity_date': '2026-08-01',
                'followup_text': 'Should be rejected',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SalesActivity.query.count(), 0)

        response = self.client.post(
            '/sales-activities/add',
            data={
                'activity_type': 'Remote Engagement', 'source_type': 'Other',
                'company': 'Manual Company', 'activity_date': '2026-08-01',
                'followup_text': 'Manual source follow-up',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SalesActivity.query.one().company, 'Manual Company')

    def test_search_includes_unqualified_and_deal_lost_records(self):
        lead = self._lead(company='Unqualified Search Co', status='Unqualified')
        pipeline = Pipeline(
            name='Lost Contact', company='Deal Lost Search Co', owner_id=self.admin_id,
            stage='6b) Deal Lost', mrc_usd=0, otc_usd=0, contract_term_yrs=1,
            gp_margin=0, win_rate=0,
        )
        db.session.add(pipeline)
        db.session.commit()

        lead_data = self.client.get('/sales-activities/source-search?source_type=Sales%20Leads&q=Unqualified').get_json()
        pipeline_data = self.client.get('/sales-activities/source-search?source_type=Pipeline&q=Deal%20Lost').get_json()
        self.assertIn(lead.id, [item['id'] for item in lead_data['items']])
        self.assertIn(pipeline.id, [item['id'] for item in pipeline_data['items']])
        self.assertIn('Unqualified', [item['status'] for item in lead_data['items']])
        self.assertIn('6b) Deal Lost', [item['status'] for item in pipeline_data['items']])

    def test_qualified_conversion_rejects_long_requirements_with_clear_message(self):
        lead = self._lead(requirements='R' * 201)
        response = self.client.post(
            f'/leads/{lead.id}/quick-update',
            json={'field': 'leads_status', 'value': 'Qualified'},
        )
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertIn('200 characters', payload['error'])
        self.assertIn('Note', payload['error'])
        self.assertEqual(Pipeline.query.count(), 0)

    def test_soft_delete_keeps_snapshot_and_hides_record(self):
        lead = self._lead(company='Archived Company')
        response = self.client.post(f'/leads/{lead.id}/delete')
        self.assertEqual(response.status_code, 302)
        db.session.refresh(lead)
        self.assertTrue(lead.is_deleted)
        archive = DeletedRecord.query.filter_by(entity_type='sales_lead', entity_id=lead.id).one()
        self.assertIn('Archived Company', archive.data_snapshot)
        page = self.client.get('/leads/')
        self.assertNotIn(b'Archived Company', page.data)

    def test_legacy_sales_activity_terminology_is_migrated(self):
        lead = self._lead(company='Legacy Terminology Co')
        activity = SalesActivity(
            activity_type=SalesActivity.TYPE_REMOTE_ENGAGEMENT,
            remote_engagement_subtype='Follow-up',
            source_type='Sales Leads',
            sales_lead_id=lead.id,
            company=lead.company,
            activity_date=date(2026, 8, 1),
            status='Completed',
            owner_id=self.admin_id,
        )
        task = Task(
            content='Field Visit follow-up: Legacy Terminology Co',
            due_date=date(2026, 8, 1),
            owner_id=self.admin_id,
            sales_lead_id=lead.id,
            company=lead.company,
        )
        db.session.add_all([activity, task])
        db.session.commit()
        activity_id = activity.id
        task_id = task.id

        db.session.execute(text(
            'ALTER TABLE sales_activities '
            'RENAME COLUMN remote_engagement_subtype TO online_subtype'
        ))
        db.session.execute(
            text('UPDATE sales_activities SET activity_type = :legacy_type WHERE id = :activity_id'),
            {'legacy_type': 'Online', 'activity_id': activity_id},
        )
        db.session.commit()

        ensure_sales_activity_columns()
        ensure_sales_activity_terminology()
        db.session.expire_all()

        migrated = db.session.get(SalesActivity, activity_id)
        migrated_task = db.session.get(Task, task_id)
        self.assertEqual(migrated.activity_type, 'Remote Engagement')
        self.assertEqual(migrated.remote_engagement_subtype, 'Follow-up')
        self.assertIn('On-site Visit follow-up', migrated_task.content)

    def test_activity_status_and_deadline_indicators_are_time_based(self):
        lead = self._lead(company='Status Rules Co')
        future_visit = SalesActivity(
            activity_type=SalesActivity.TYPE_ON_SITE_VISIT, source_type='Sales Leads',
            sales_lead_id=lead.id, company=lead.company, activity_date=date(2026, 8, 6),
            estimated_start_at=datetime(2026, 8, 6, 12, 0),
            estimated_end_at=datetime(2026, 8, 6, 13, 0),
            status='Scheduled', owner_id=self.admin_id,
        )
        past_visit = SalesActivity(
            activity_type=SalesActivity.TYPE_ON_SITE_VISIT, source_type='Sales Leads',
            sales_lead_id=lead.id, company=lead.company, activity_date=date(2026, 7, 31),
            estimated_start_at=datetime(2026, 7, 31, 12, 0),
            estimated_end_at=datetime(2026, 7, 31, 13, 0),
            status='Scheduled', owner_id=self.admin_id,
        )
        due_today = SalesActivity(
            activity_type=SalesActivity.TYPE_REMOTE_ENGAGEMENT,
            remote_engagement_subtype='Next Steps / To-do', source_type='Sales Leads',
            sales_lead_id=lead.id, company=lead.company, activity_date=date(2026, 8, 1),
            status='Scheduled', owner_id=self.admin_id,
        )
        completed = SalesActivity(
            activity_type=SalesActivity.TYPE_REMOTE_ENGAGEMENT,
            remote_engagement_subtype='Follow-up', source_type='Sales Leads',
            sales_lead_id=lead.id, company=lead.company, activity_date=date(2026, 7, 31),
            status='Completed', owner_id=self.admin_id,
        )
        db.session.add_all([future_visit, past_visit, due_today, completed])
        db.session.commit()
        now = datetime(2026, 8, 1, 10, 0)

        self.assertEqual(future_visit.get_display_status(now), 'Scheduled')
        self.assertIsNone(future_visit.get_deadline_indicator(now))
        self.assertEqual(past_visit.get_display_status(now), 'Follow-up Required')
        self.assertEqual(past_visit.get_deadline_indicator(now), 'Overdue')
        self.assertEqual(due_today.get_display_status(now), 'Follow-up Required')
        self.assertEqual(due_today.get_deadline_indicator(now), 'Due Today')
        self.assertEqual(completed.get_display_status(now), 'Completed')
        self.assertIsNone(completed.get_deadline_indicator(now))

    def test_open_activity_can_be_rescheduled_and_linked_task_is_synchronised(self):
        lead = self._lead(company='Reschedule Co')
        self.client.post('/sales-activities/add', data={
            'activity_type': 'On-site Visit', 'source_type': 'Sales Leads',
            'sales_lead_id': str(lead.id), 'company': lead.company,
            'start_date': '2026-08-06', 'start_time': '10:00',
            'end_date': '2026-08-06', 'end_time': '11:00',
            'address': 'Old address', 'owner_id': str(self.admin_id),
        })
        activity = SalesActivity.query.one()
        task = Task.query.one()

        response = self.client.post(f'/sales-activities/{activity.id}/edit', data={
            'start_date': '2026-08-07', 'start_time': '14:00',
            'end_date': '2026-08-08', 'end_time': '09:30',
            'address': 'New customer office', 'owner_id': str(self.admin_id),
            'contact_name[]': ['Alice'], 'contact_position[]': ['CTO'],
            'contact_information[]': ['alice@example.com'],
            'purpose_project': 'Updated workshop', 'expected_result': 'Confirm scope',
            'remarks': 'Customer requested a new time',
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        db.session.refresh(activity)
        db.session.refresh(task)
        self.assertEqual(activity.activity_date, date(2026, 8, 7))
        self.assertEqual(activity.estimated_start_at, datetime(2026, 8, 7, 14, 0))
        self.assertEqual(activity.estimated_end_at, datetime(2026, 8, 8, 9, 30))
        self.assertEqual(activity.address, 'New customer office')
        self.assertEqual(activity.contacts[0].contact_name, 'Alice')
        self.assertEqual(task.due_date, date(2026, 8, 8))
        self.assertEqual(activity.status, 'Scheduled')
        self.assertIn(b'Sales Activity updated successfully!', response.data)
        self.assertIsNotNone(ActivityLog.query.filter_by(action_type='Sales Activity - Rescheduled').first())

    def test_cancelling_activity_retains_history_and_cancels_linked_task(self):
        lead = self._lead(company='Cancelled Visit Co')
        self.client.post('/sales-activities/add', data={
            'activity_type': 'On-site Visit', 'source_type': 'Sales Leads',
            'sales_lead_id': str(lead.id), 'company': lead.company,
            'start_date': '2026-08-06', 'start_time': '10:00',
            'end_date': '2026-08-06', 'end_time': '11:00',
            'owner_id': str(self.admin_id),
        })
        activity = SalesActivity.query.one()
        task = Task.query.one()

        response = self.client.post(
            f'/sales-activities/{activity.id}/cancel',
            data={'cancellation_reason': 'Customer requested postponement without a new date.'},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        db.session.refresh(activity)
        db.session.refresh(task)
        self.assertEqual(activity.status, 'Cancelled')
        self.assertEqual(task.status, 'Cancelled')
        self.assertFalse(activity.is_deleted)
        self.assertEqual(activity.get_display_status(datetime(2026, 8, 10)), 'Cancelled')
        self.assertIsNone(activity.get_deadline_indicator(datetime(2026, 8, 10)))
        self.assertIn('Customer requested postponement', activity.cancellation_reason)

    def test_legacy_pending_status_is_migrated_to_scheduled(self):
        lead = self._lead(company='Legacy Status Co')
        activity = SalesActivity(
            activity_type=SalesActivity.TYPE_ON_SITE_VISIT, source_type='Sales Leads',
            sales_lead_id=lead.id, company=lead.company, activity_date=date(2026, 8, 6),
            estimated_start_at=datetime(2026, 8, 6, 10, 0),
            estimated_end_at=datetime(2026, 8, 6, 11, 0),
            status='Pending Follow-up', owner_id=self.admin_id,
        )
        db.session.add(activity)
        db.session.commit()
        ensure_sales_activity_statuses()
        db.session.refresh(activity)
        self.assertEqual(activity.status, 'Scheduled')

    def test_legacy_activities_and_log_clear_routes_are_removed(self):
        self.assertEqual(self.client.get('/activities').status_code, 404)
        self.assertEqual(self.client.post('/admin/login-logs/clear').status_code, 404)
        self._lead(company='Logged Company')
        self.assertGreaterEqual(ActivityLog.query.count(), 1)  # Login is retained.
        page = self.client.get('/admin/login-logs')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Login', page.data)

    def test_calendar_month_navigation_context_and_multi_date_selection(self):
        lead = self._lead()
        for activity_day in ('2026-08-02', '2026-08-11'):
            self.client.post(
                '/sales-activities/add',
                data={
                    'activity_type': 'Remote Engagement', 'source_type': 'Sales Leads',
                    'sales_lead_id': str(lead.id), 'company': lead.company,
                    'activity_date': activity_day, 'followup_text': f'Follow-up {activity_day}',
                },
            )
        response = self.client.get(
            '/sales-activities/?calendar_month=2026-08&dates=2026-08-02&dates=2026-08-11'
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'2026-08-02', response.data)
        self.assertIn(b'2026-08-11', response.data)
        self.assertIn(b'previousCalendarMonth', response.data)
        self.assertIn(b'nextCalendarMonth', response.data)


if __name__ == '__main__':
    unittest.main()
