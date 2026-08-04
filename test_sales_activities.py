import os
import tempfile
import unittest
from datetime import date, datetime, timedelta

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

    def test_customer_visit_supports_cross_date_schedule_and_feedback_sync(self):
        lead = self._lead()
        response = self.client.post(
            '/sales-activities/add',
            data={
                'activity_type': 'Customer Visit',
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

        activity_list = self.client.get('/sales-activities/')
        self.assertEqual(activity_list.status_code, 200)
        activity_html = activity_list.get_data(as_text=True)
        self.assertIn('<strong class="activity-schedule-start">2026-07-30 23:00</strong>', activity_html)
        self.assertIn('<small class="activity-schedule-end">→ 2026-07-31 01:00</small>', activity_html)
        self.assertEqual(len(activity.contacts), 2)
        self.assertEqual(task.sales_activity_id, activity.id)
        self.assertIn('Customer Visit scheduled', lead.follow_up)

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
        self.assertIn('Customer Visit feedback: Customer approved', lead.follow_up)
        self.assertIn('Send final migration plan.', lead.follow_up)
        self.assertEqual(SalesActivity.query.count(), 2)
        next_step_activity = SalesActivity.query.filter_by(remote_engagement_subtype='Next Steps / To-do').one()
        self.assertEqual(next_step_activity.status, 'Scheduled')
        self.assertEqual(Task.query.count(), 2)

    def test_dc_site_visit_uses_visit_schedule_task_and_feedback_workflow(self):
        lead = self._lead(company='DC Visitor Co')
        response = self.client.post(
            '/sales-activities/add',
            data={
                'activity_type': 'DC Site Visit',
                'source_type': 'Sales Leads',
                'sales_lead_id': str(lead.id),
                'company': lead.company,
                'start_date': '2026-08-01',
                'start_time': '10:00',
                'end_date': '2026-08-01',
                'end_time': '12:00',
                'owner_id': str(self.admin_id),
                'address': 'BIT Data Center - Lobby',
                'contact_name[]': ['Customer CTO'],
                'contact_position[]': ['CTO'],
                'contact_information[]': ['cto@example.com'],
                'purpose_project': 'Facility and security tour',
                'expected_result': 'Confirm technical requirements',
            },
        )
        self.assertEqual(response.status_code, 302)
        activity = SalesActivity.query.one()
        task = Task.query.one()
        self.assertEqual(activity.activity_type, SalesActivity.TYPE_DC_SITE_VISIT)
        self.assertTrue(activity.is_scheduled_visit)
        self.assertEqual(activity.activity_date, date(2026, 8, 1))
        self.assertEqual(activity.estimated_start_at, datetime(2026, 8, 1, 10, 0))
        self.assertEqual(activity.estimated_end_at, datetime(2026, 8, 1, 12, 0))
        self.assertIn('DC Site Visit follow-up', task.content)
        self.assertIn('DC Site Visit scheduled', lead.follow_up)

        response = self.client.post(
            f'/tasks/{task.id}/complete',
            data={'completion_notes': 'Completed directly from Tasks'},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        db.session.refresh(activity)
        db.session.refresh(task)
        self.assertEqual(activity.status, SalesActivity.STATUS_SCHEDULED)
        self.assertNotEqual(task.status, 'Completed')

        response = self.client.post(
            f'/sales-activities/{activity.id}/followup',
            data={'completion_notes': 'Customer approved the facility and security design.'},
        )
        self.assertEqual(response.status_code, 302)
        db.session.refresh(activity)
        db.session.refresh(task)
        self.assertEqual(activity.status, SalesActivity.STATUS_COMPLETED)
        self.assertEqual(task.status, 'Completed')
        self.assertIn('DC Site Visit feedback: Customer approved', lead.follow_up)

    def test_invalid_customer_visit_reopens_form_and_uses_start_date_as_activity_date(self):
        lead = self._lead(company='Retained Visit Form Co')
        data = {
            'activity_type': 'Customer Visit',
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

    def test_add_sales_activity_defaults_to_customer_visit(self):
        response = self.client.get('/sales-activities/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<option value="Customer Visit" selected>', response.data)
        self.assertIn(b'<th>Date</th>', response.data)
        self.assertIn(b'min-width: 1900px', response.data)
        self.assertIn(b'sales-activity-table-wrapper', response.data)
        self.assertNotIn(b'<th>Remote Engagement Subtype</th>', response.data)
        self.assertLess(
            response.data.index(b'for="typeCustomerVisit"'),
            response.data.index(b'for="typeRemoteEngagement"'),
        )

    def test_activity_list_paginates_twenty_records_and_preserves_filters(self):
        base_date = date(2026, 8, 1)
        for index in range(1, 26):
            db.session.add(SalesActivity(
                activity_type=SalesActivity.TYPE_REMOTE_ENGAGEMENT,
                remote_engagement_subtype='Follow-up',
                source_type='Other',
                company=f'Paged Activity {index:02d}',
                activity_date=base_date + timedelta(days=index),
                status=SalesActivity.STATUS_COMPLETED,
                owner_id=self.admin_id,
            ))
        db.session.commit()

        query_string = (
            f'type=Remote%20Engagement&start_date=2026-08-01&'
            f'end_date=2026-09-30&owner_id={self.admin_id}'
        )
        first_page = self.client.get(f'/sales-activities/?{query_string}')
        self.assertEqual(first_page.status_code, 200)
        self.assertIn(b'Showing 1-20 of 25 records', first_page.data)
        self.assertIn(b'Paged Activity 25', first_page.data)
        self.assertIn(b'Paged Activity 06', first_page.data)
        self.assertNotIn(b'Paged Activity 05', first_page.data)
        self.assertIn(b'page=2', first_page.data)
        self.assertIn(b'type=Remote+Engagement', first_page.data)
        self.assertIn(b'start_date=2026-08-01', first_page.data)

        second_page = self.client.get(f'/sales-activities/?{query_string}&page=2')
        self.assertEqual(second_page.status_code, 200)
        self.assertIn(b'Showing 21-25 of 25 records', second_page.data)
        self.assertIn(b'Paged Activity 05', second_page.data)
        self.assertIn(b'Paged Activity 01', second_page.data)
        self.assertNotIn(b'Paged Activity 25', second_page.data)

    def test_owner_summary_groups_due_and_overdue_reminders_into_follow_up_required(self):
        now = datetime.now()
        activities = [
            SalesActivity(
                activity_type=SalesActivity.TYPE_CUSTOMER_VISIT,
                source_type='Other', company='Scheduled Summary Activity',
                activity_date=(now + timedelta(days=2)).date(),
                estimated_start_at=now + timedelta(days=2),
                estimated_end_at=now + timedelta(days=2, hours=1),
                status=SalesActivity.STATUS_SCHEDULED, owner_id=self.admin_id,
            ),
            SalesActivity(
                activity_type=SalesActivity.TYPE_CUSTOMER_VISIT,
                source_type='Other', company='Follow-up Summary Activity',
                activity_date=(now - timedelta(hours=2)).date(),
                estimated_start_at=now - timedelta(hours=3),
                estimated_end_at=now - timedelta(hours=2),
                status=SalesActivity.STATUS_SCHEDULED, owner_id=self.admin_id,
            ),
            SalesActivity(
                activity_type=SalesActivity.TYPE_CUSTOMER_VISIT,
                source_type='Other', company='Overdue Summary Activity',
                activity_date=(now - timedelta(days=2)).date(),
                estimated_start_at=now - timedelta(days=2, hours=1),
                estimated_end_at=now - timedelta(days=2),
                status=SalesActivity.STATUS_SCHEDULED, owner_id=self.admin_id,
            ),
            SalesActivity(
                activity_type=SalesActivity.TYPE_REMOTE_ENGAGEMENT,
                remote_engagement_subtype='Next Steps / To-do',
                source_type='Other', company='Due Today Summary Activity',
                activity_date=now.date(), status=SalesActivity.STATUS_SCHEDULED,
                owner_id=self.admin_id,
            ),
            SalesActivity(
                activity_type=SalesActivity.TYPE_REMOTE_ENGAGEMENT,
                remote_engagement_subtype='Follow-up', source_type='Other',
                company='Completed Summary Activity', activity_date=now.date(),
                status=SalesActivity.STATUS_COMPLETED, owner_id=self.admin_id,
            ),
            SalesActivity(
                activity_type=SalesActivity.TYPE_REMOTE_ENGAGEMENT,
                remote_engagement_subtype='Follow-up', source_type='Other',
                company='Cancelled Summary Activity', activity_date=now.date(),
                status=SalesActivity.STATUS_CANCELLED, owner_id=self.admin_id,
            ),
        ]
        db.session.add_all(activities)
        db.session.commit()

        response = self.client.get('/sales-activities/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        summary_start = html.index('Activities by Owner')
        summary_end = html.index('</table>', summary_start)
        summary_html = html[summary_start:summary_end]

        self.assertNotIn('Remote Engagement</th>', summary_html)
        self.assertNotIn('Customer Visit</th>', summary_html)
        for status in ('Scheduled', 'Follow-up Required', 'Completed', 'Cancelled'):
            self.assertIn(f'>{status}</th>', summary_html)
        self.assertNotIn('>Due Today</th>', summary_html)
        self.assertNotIn('>Overdue</th>', summary_html)
        self.assertIn(
            '<tr><td>Admin</td><td>1</td><td>3</td><td>1</td><td>1</td><td class="summary-total-column">6</td></tr>',
            summary_html,
        )
        self.assertIn(
            '<td>Total</td><td>1</td><td>3</td><td>1</td><td>1</td><td class="summary-total-column">6</td>',
            summary_html,
        )
        self.assertTrue(summary_html.index('>Cancelled</th>') < summary_html.index('>Total</th>'))

        source_start = html.index('Source Type by Owner')
        source_end = html.index('</table>', source_start)
        source_summary_html = html[source_start:source_end]
        self.assertTrue(source_summary_html.index('>Other</th>') < source_summary_html.index('>Total</th>'))
        self.assertIn('<th class="summary-total-column">Total</th>', source_summary_html)
        self.assertIn('<td class="summary-total-column">6</td>', source_summary_html)

    def test_admin_owner_filter_supports_multiple_owners(self):
        owner_a = User(username='Owner Alpha', role='sales')
        owner_a.set_password('bitcrm')
        owner_b = User(username='Owner Beta', role='sales')
        owner_b.set_password('bitcrm')
        db.session.add_all([owner_a, owner_b])
        db.session.flush()

        db.session.add_all([
            SalesActivity(
                activity_type=SalesActivity.TYPE_REMOTE_ENGAGEMENT,
                remote_engagement_subtype='Follow-up', source_type='Other',
                company='Alpha Selected Activity', activity_date=date.today(),
                status=SalesActivity.STATUS_COMPLETED, owner_id=owner_a.id,
            ),
            SalesActivity(
                activity_type=SalesActivity.TYPE_REMOTE_ENGAGEMENT,
                remote_engagement_subtype='Follow-up', source_type='Other',
                company='Beta Selected Activity', activity_date=date.today(),
                status=SalesActivity.STATUS_COMPLETED, owner_id=owner_b.id,
            ),
            SalesActivity(
                activity_type=SalesActivity.TYPE_REMOTE_ENGAGEMENT,
                remote_engagement_subtype='Follow-up', source_type='Other',
                company='Admin Excluded Activity', activity_date=date.today(),
                status=SalesActivity.STATUS_COMPLETED, owner_id=self.admin_id,
            ),
        ])
        db.session.commit()

        response = self.client.get(
            f'/sales-activities/?owner_id={owner_a.id}&owner_id={owner_b.id}'
        )
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Alpha Selected Activity', html)
        self.assertIn('Beta Selected Activity', html)
        self.assertNotIn('Admin Excluded Activity', html)
        self.assertIn('id="activityOwnerFilterButton"', html)
        self.assertIn('id="allOwnersFilter"', html)
        self.assertIn('card mb-4 activity-filter-card', html)
        self.assertIn('.activity-filter-card { position: relative; z-index: 20; overflow: visible; }', html)
        self.assertIn('.owner-filter-dropdown { position: relative; z-index: 1020; }', html)
        self.assertIn(
            f'value="{owner_a.id}" checked', html
        )
        self.assertIn(
            f'value="{owner_b.id}" checked', html
        )
        self.assertIn('owner-filter-checkbox', html)
        self.assertIn('applyActivityFilterImmediately();', html)
        self.assertNotIn('window.setTimeout(applyActivityFilterImmediately', html)
        self.assertNotIn('Hold Ctrl/Cmd to select multiple', html)
        self.assertNotIn('type="submit" class="btn btn-primary">Filter', html)

        summary_start = html.index('Activities by Owner')
        summary_end = html.index('</table>', summary_start)
        summary_html = html[summary_start:summary_end]
        self.assertIn(
            '<tr><td>Owner Alpha</td><td>0</td><td>0</td><td>1</td><td>0</td><td class="summary-total-column">1</td></tr>',
            summary_html,
        )
        self.assertIn(
            '<tr><td>Owner Beta</td><td>0</td><td>0</td><td>1</td><td>0</td><td class="summary-total-column">1</td></tr>',
            summary_html,
        )
        self.assertNotIn('<td>Admin</td>', summary_html)
        self.assertIn(
            '<td>Total</td><td>0</td><td>0</td><td>2</td><td>0</td><td class="summary-total-column">2</td>',
            summary_html,
        )

    def test_non_admin_sees_only_their_own_owner_summary(self):
        sales_user = User(username='Sales User', role='sales')
        sales_user.set_password('bitcrm')
        db.session.add(sales_user)
        db.session.flush()
        sales_user_id = sales_user.id

        db.session.add_all([
            SalesActivity(
                activity_type=SalesActivity.TYPE_REMOTE_ENGAGEMENT,
                remote_engagement_subtype='Follow-up', source_type='Other',
                company='Sales User Activity', activity_date=date.today(),
                status=SalesActivity.STATUS_COMPLETED, owner_id=sales_user_id,
            ),
            SalesActivity(
                activity_type=SalesActivity.TYPE_REMOTE_ENGAGEMENT,
                remote_engagement_subtype='Follow-up', source_type='Other',
                company='Admin Private Activity', activity_date=date.today(),
                status=SalesActivity.STATUS_COMPLETED, owner_id=self.admin_id,
            ),
        ])
        db.session.commit()

        self.client.get('/logout')
        response = self.client.post(
            '/login', data={'username': 'Sales User', 'password': 'bitcrm'},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.get('/sales-activities/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        summary_start = html.index('Activities by Owner')
        summary_end = html.index('</table>', summary_start)
        summary_html = html[summary_start:summary_end]

        self.assertIn(
            '<tr><td>Sales User</td><td>0</td><td>0</td><td>1</td><td>0</td><td class="summary-total-column">1</td></tr>',
            summary_html,
        )
        self.assertNotIn('<td>Admin</td>', summary_html)
        self.assertIn('Sales User Activity', html)
        self.assertNotIn('Admin Private Activity', html)

    def test_type_and_date_filters_include_overlapping_cross_date_visits(self):
        records = [
            SalesActivity(
                activity_type=SalesActivity.TYPE_REMOTE_ENGAGEMENT,
                remote_engagement_subtype='Follow-up', source_type='Other',
                company='Remote In Range', activity_date=date(2026, 8, 10),
                status=SalesActivity.STATUS_COMPLETED, owner_id=self.admin_id,
            ),
            SalesActivity(
                activity_type=SalesActivity.TYPE_REMOTE_ENGAGEMENT,
                remote_engagement_subtype='Follow-up', source_type='Other',
                company='Remote Outside Range', activity_date=date(2026, 8, 8),
                status=SalesActivity.STATUS_COMPLETED, owner_id=self.admin_id,
            ),
            SalesActivity(
                activity_type=SalesActivity.TYPE_CUSTOMER_VISIT,
                source_type='Other', company='Cross-date Visit In Range',
                activity_date=date(2026, 8, 9),
                estimated_start_at=datetime(2026, 8, 9, 23, 0),
                estimated_end_at=datetime(2026, 8, 10, 1, 0),
                status=SalesActivity.STATUS_SCHEDULED, owner_id=self.admin_id,
            ),
            SalesActivity(
                activity_type=SalesActivity.TYPE_CUSTOMER_VISIT,
                source_type='Other', company='Visit Outside Range',
                activity_date=date(2026, 8, 11),
                estimated_start_at=datetime(2026, 8, 11, 9, 0),
                estimated_end_at=datetime(2026, 8, 11, 10, 0),
                status=SalesActivity.STATUS_SCHEDULED, owner_id=self.admin_id,
            ),
        ]
        db.session.add_all(records)
        db.session.commit()

        visit_response = self.client.get(
            '/sales-activities/?type=Out+of+Building+Visit&start_date=2026-08-10&end_date=2026-08-10'
        )
        self.assertEqual(visit_response.status_code, 200)
        self.assertIn(b'Cross-date Visit In Range', visit_response.data)
        self.assertNotIn(b'Remote In Range', visit_response.data)
        self.assertNotIn(b'Remote Outside Range', visit_response.data)
        self.assertNotIn(b'Visit Outside Range', visit_response.data)
        self.assertIn(b'<td class="summary-total-column">1</td>', visit_response.data)

        remote_response = self.client.get(
            '/sales-activities/?type=Remote+Engagement&start_date=2026-08-10&end_date=2026-08-10'
        )
        self.assertEqual(remote_response.status_code, 200)
        self.assertIn(b'Remote In Range', remote_response.data)
        self.assertNotIn(b'Cross-date Visit In Range', remote_response.data)
        self.assertNotIn(b'Remote Outside Range', remote_response.data)
        self.assertIn(b'<td class="summary-total-column">1</td>', remote_response.data)

        calendar_date_response = self.client.get('/sales-activities/?dates=2026-08-10')
        self.assertEqual(calendar_date_response.status_code, 200)
        self.assertIn(b'Remote In Range', calendar_date_response.data)
        self.assertIn(b'Cross-date Visit In Range', calendar_date_response.data)
        self.assertNotIn(b'Remote Outside Range', calendar_date_response.data)
        self.assertNotIn(b'Visit Outside Range', calendar_date_response.data)

        reversed_range_response = self.client.get(
            '/sales-activities/?start_date=2026-08-10&end_date=2026-08-09'
        )
        self.assertEqual(reversed_range_response.status_code, 200)
        self.assertIn(b'Remote In Range', reversed_range_response.data)
        self.assertIn(b'Cross-date Visit In Range', reversed_range_response.data)
        self.assertNotIn(b'Remote Outside Range', reversed_range_response.data)
        self.assertNotIn(b'Visit Outside Range', reversed_range_response.data)
        self.assertIn(b'name="start_date" value="2026-08-09"', reversed_range_response.data)
        self.assertIn(b'name="end_date" value="2026-08-10"', reversed_range_response.data)

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
        legacy_visit = SalesActivity(
            activity_type=SalesActivity.TYPE_CUSTOMER_VISIT,
            source_type='Sales Leads',
            sales_lead_id=lead.id,
            company=lead.company,
            activity_date=date(2026, 8, 1),
            estimated_start_at=datetime(2026, 8, 1, 9, 0),
            estimated_end_at=datetime(2026, 8, 1, 10, 0),
            status='Scheduled',
            owner_id=self.admin_id,
        )
        task = Task(
            content='Field Visit from Marketing Event follow-up: Legacy Terminology Co',
            due_date=date(2026, 8, 1),
            owner_id=self.admin_id,
            sales_lead_id=lead.id,
            company=lead.company,
        )
        db.session.add_all([activity, legacy_visit, task])
        db.session.commit()
        activity_id = activity.id
        legacy_visit_id = legacy_visit.id
        task_id = task.id

        db.session.execute(text(
            'ALTER TABLE sales_activities '
            'RENAME COLUMN remote_engagement_subtype TO online_subtype'
        ))
        db.session.execute(
            text('UPDATE sales_activities SET activity_type = :legacy_type WHERE id = :activity_id'),
            {'legacy_type': 'Online', 'activity_id': activity_id},
        )
        db.session.execute(
            text('UPDATE sales_activities SET activity_type = :legacy_type WHERE id = :activity_id'),
            {'legacy_type': 'On-site Visit', 'activity_id': legacy_visit_id},
        )
        db.session.execute(
            text('UPDATE sales_activities SET source_type = :legacy_source WHERE id = :activity_id'),
            {'legacy_source': 'Marketing Event', 'activity_id': legacy_visit_id},
        )
        db.session.commit()

        ensure_sales_activity_columns()
        ensure_sales_activity_terminology()
        db.session.expire_all()

        migrated = db.session.get(SalesActivity, activity_id)
        migrated_visit = db.session.get(SalesActivity, legacy_visit_id)
        migrated_task = db.session.get(Task, task_id)
        self.assertEqual(migrated.activity_type, 'Remote Engagement')
        self.assertEqual(migrated.remote_engagement_subtype, 'Follow-up')
        self.assertEqual(migrated_visit.activity_type, 'Customer Visit')
        self.assertEqual(migrated_visit.source_type, 'Event')
        self.assertIn('Customer Visit from Event follow-up', migrated_task.content)

    def test_event_source_is_available_and_legacy_requests_are_normalized(self):
        lead = self._lead(company='Event Prospect')
        lead.event = 'Cloud Expo'
        db.session.commit()

        event_search = self.client.get(
            '/sales-activities/source-search?source_type=Event&q=Cloud%20Expo'
        ).get_json()
        legacy_search = self.client.get(
            '/sales-activities/source-search?source_type=Marketing%20Event&q=Cloud%20Expo'
        ).get_json()
        self.assertIn('Event Prospect', [item['company'] for item in event_search['items']])
        self.assertEqual(event_search, legacy_search)

        response = self.client.post(
            '/sales-activities/add',
            data={
                'activity_type': 'Remote Engagement',
                'source_type': 'Marketing Event',
                'company': 'Legacy Event Company',
                'activity_date': '2026-08-04',
                'followup_text': 'Legacy source request remains compatible.',
            },
        )
        self.assertEqual(response.status_code, 302)
        activity = SalesActivity.query.filter_by(company='Legacy Event Company').one()
        self.assertEqual(activity.source_type, 'Event')

        page = self.client.get('/sales-activities/').get_data(as_text=True)
        self.assertIn('>Event</th>', page)
        self.assertIn('value="Event"', page)
        self.assertNotIn('Marketing Event', page)

    def test_activity_status_and_deadline_indicators_are_time_based(self):
        lead = self._lead(company='Status Rules Co')
        future_visit = SalesActivity(
            activity_type=SalesActivity.TYPE_CUSTOMER_VISIT, source_type='Sales Leads',
            sales_lead_id=lead.id, company=lead.company, activity_date=date(2026, 8, 6),
            estimated_start_at=datetime(2026, 8, 6, 12, 0),
            estimated_end_at=datetime(2026, 8, 6, 13, 0),
            status='Scheduled', owner_id=self.admin_id,
        )
        recently_ended_visit = SalesActivity(
            activity_type=SalesActivity.TYPE_CUSTOMER_VISIT, source_type='Sales Leads',
            sales_lead_id=lead.id, company=lead.company, activity_date=date(2026, 7, 31),
            estimated_start_at=datetime(2026, 7, 31, 12, 0),
            estimated_end_at=datetime(2026, 7, 31, 13, 0),
            status='Scheduled', owner_id=self.admin_id,
        )
        overdue_visit = SalesActivity(
            activity_type=SalesActivity.TYPE_CUSTOMER_VISIT, source_type='Sales Leads',
            sales_lead_id=lead.id, company=lead.company, activity_date=date(2026, 7, 31),
            estimated_start_at=datetime(2026, 7, 31, 8, 0),
            estimated_end_at=datetime(2026, 7, 31, 9, 0),
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
        db.session.add_all([future_visit, recently_ended_visit, overdue_visit, due_today, completed])
        db.session.flush()
        recently_ended_task = Task(
            content='Recent visit feedback', due_date=recently_ended_visit.estimated_end_at.date(),
            status='In Progress', owner_id=self.admin_id, sales_activity_id=recently_ended_visit.id,
        )
        overdue_task = Task(
            content='Overdue visit feedback', due_date=overdue_visit.estimated_end_at.date(),
            status='In Progress', owner_id=self.admin_id, sales_activity_id=overdue_visit.id,
        )
        db.session.add_all([recently_ended_task, overdue_task])
        db.session.commit()
        now = datetime(2026, 8, 1, 10, 0)

        self.assertEqual(future_visit.get_display_status(now), 'Scheduled')
        self.assertIsNone(future_visit.get_deadline_indicator(now))
        self.assertEqual(recently_ended_visit.get_display_status(now), 'Follow-up Required')
        self.assertIsNone(recently_ended_visit.get_deadline_indicator(now))
        self.assertFalse(recently_ended_task.check_overdue(now))
        self.assertEqual(recently_ended_task.status, 'In Progress')
        self.assertEqual(overdue_visit.get_display_status(now), 'Follow-up Required')
        self.assertEqual(overdue_visit.get_deadline_indicator(now), 'Overdue')
        self.assertTrue(overdue_task.check_overdue(now))
        self.assertEqual(overdue_task.status, 'Overdue')
        self.assertEqual(due_today.get_display_status(now), 'Follow-up Required')
        self.assertEqual(due_today.get_deadline_indicator(now), 'Due Today')
        self.assertEqual(completed.get_display_status(now), 'Completed')
        self.assertIsNone(completed.get_deadline_indicator(now))

    def test_open_activity_can_be_rescheduled_and_linked_task_is_synchronised(self):
        lead = self._lead(company='Reschedule Co')
        self.client.post('/sales-activities/add', data={
            'activity_type': 'Customer Visit', 'source_type': 'Sales Leads',
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
            'activity_type': 'Customer Visit', 'source_type': 'Sales Leads',
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
            activity_type=SalesActivity.TYPE_CUSTOMER_VISIT, source_type='Sales Leads',
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

    def test_sales_activity_manual_is_available_in_english_and_chinese(self):
        english = self.client.get('/manual')
        self.assertEqual(english.status_code, 200)
        english_html = english.get_data(as_text=True)
        for phrase in (
            'BITCRM User Guide',
            'Getting started',
            'Dashboard',
            'Sales Leads',
            'Pipeline',
            'Sales Activities',
            'Tasks',
            'User Management',
            'Login Logs &amp; Archive',
            'Customer Visit',
            'DC Site Visit',
            'Remote Engagement',
            'Owner',
            '20 records per page',
            'Updated August 4, 2026',
        ):
            self.assertIn(phrase, english_html)

        with self.client.session_transaction() as session:
            session['lang'] = 'zh'
        chinese = self.client.get('/manual')
        self.assertEqual(chinese.status_code, 200)
        chinese_html = chinese.get_data(as_text=True)
        for phrase in (
            'BITCRM 使用说明',
            '快速开始',
            'Dashboard（管理看板）',
            'Sales Leads（潜在客户）',
            'Pipeline（销售机会）',
            'Sales Activities（销售活动）',
            'Tasks（待办任务）',
            '用户管理',
            '登录日志和操作归档',
            '客户拜访',
            '数据中心参观',
            '远程沟通',
            '20条',
            '更新于2026年8月4日',
        ):
            self.assertIn(phrase, chinese_html)

    def test_calendar_marks_today_without_replacing_status_backgrounds(self):
        response = self.client.get('/sales-activities/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('.calendar-day.is-today .day-number', html)
        self.assertIn('background: #0d6efd', html)
        self.assertIn('.calendar-day.has-red { background: #f8d7da; }', html)
        self.assertIn('.calendar-day.has-green { background: #d1e7dd; }', html)
        self.assertIn('const isToday = iso === todayIso', html)
        self.assertIn("' is-today'", html)
        self.assertIn('class="today-label"', html)
        self.assertIn('aria-current', html)

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
