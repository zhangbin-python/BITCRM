# BITCRM Sales Activities Implementation Plan

## 1. Terminology and Existing System Vocabulary

The implementation will reuse the existing system labels wherever they already exist:

- `Sales Leads`
- `Pipeline`
- `Follow-up`
- `Follow-up History`
- `Follow-up Notes`
- `Current Stuckpoint`
- `Next Steps / To-do`
- `To-do Due Date`
- `Tasks`
- `In Progress`, `Overdue`, and `Completed`
- Existing Pipeline stages and Sales Lead statuses

New labels will be introduced only where the current system has no equivalent:

- `Sales Activities`
- `Remote Engagement`
- `On-site Visit`
- `Remote Engagement Subtype`
- `Scheduled`, `Follow-up Required`, `Completed`, and `Cancelled`
- `Due Today` and `Overdue` reminder indicators
- `Existing Customer`
- `Marketing Event`
- `Expected Result`
- `Completion Notes`
- `Address`

## 2. Remove the Legacy Activities Page

The old `Activities` page is an operation/activity listing and will be removed from the user-facing application:

- Remove the `Activities` navigation item.
- Remove the `/activities` page and its page-specific frontend code.
- Remove the legacy Activities page APIs that are no longer used by the UI.
- Keep the underlying audit records and logging helpers.

The application will have one real business activity module: `Sales Activities`.

## 3. Strengthen Login Logs as the Audit Archive

The existing `Login Logs` administration entry will become the single archive view for audit records. It will retain the existing terminology and will not become a complex action-classification dashboard.

It will archive:

- Login and logout events.
- Sales Lead, Pipeline, Task, and Sales Activity create/update/delete events.
- Pipeline stage changes.
- Follow-up and `Next Steps / To-do` operations.
- Task completion, reopening, and completion notes.
- Soft-delete operations.

Each record will include the user, timestamp, action, subject, subject ID, detailed description, and IP address. Old logs will not be automatically cleared.

## 4. Sales Activities Module

The module will provide:

- `All`, `Remote Engagement`, and `On-site Visit` quick filters.
- Start/end date filtering.
- Owner filtering for administrators.
- Summary statistics by activity type and source type.
- Scheduled, follow-up-required, completed, cancelled, and overdue counts.
- An administrator-only per-owner summary.
- A month calendar with multi-date selection.
- A reverse-chronological activity table.
- An `Add Sales Activity` action.

The table will display:

- `Activity Date / Visit Date`.
- Visit start/end time for `On-site Visit`.
- `Type`.
- `Remote Engagement Subtype` where applicable.
- `Source Type`.
- `Company`.
- `Address`.
- `Contact`.
- `Position`.
- `Contact Information`.
- `Purpose / Project`.
- `Expected Result`.
- `Remarks`.
- `Owner`.
- `Status`.
- `Created At`.
- `Actions`.

## 5. Source Selection Rules

### Sales Leads

When `Source Type` is `Sales Leads`:

- Company must be selected from an asynchronous/fuzzy search of existing Sales Leads.
- Manual Company input is not allowed.
- The selected Sales Lead ID will be stored.
- Search results will include all non-deleted records, including `Qualified` and `Unqualified` leads.
- Contact, position, contact information, address, and activity details may be entered or adjusted manually for the activity.

### Pipeline

When `Source Type` is `Pipeline`:

- Company must be selected from an asynchronous/fuzzy search of existing Pipeline records.
- Manual Company input is not allowed.
- The selected Pipeline ID will be stored.
- Search results will include all non-deleted Pipeline records, including Deal Won and Deal Lost stages.
- Contact, position, contact information, address, and activity details may be entered or adjusted manually for the activity.

### Existing Customer, Marketing Event, and Other

These sources may use a manually entered Company. Existing Customer and Marketing Event may also offer fuzzy suggestions from existing CRM data, but manual entry remains allowed.

## 6. On-site Visit

An On-site Visit will support:

- Source type and linked CRM record where applicable.
- Company.
- Visit date.
- Estimated start and end time.
- Repeatable contacts with name, position, and contact information.
- Detailed address.
- Purpose / Project.
- Expected Result.
- Remarks.

Creating an On-site Visit will create a `Scheduled` Sales Activity and a linked Task. Before the visit ends it remains `Scheduled`; after the end time it displays `Follow-up Required` with an `Overdue` reminder until feedback is submitted. For Sales Leads and Pipeline sources, the planned visit will also be appended to the relevant Follow-up History. For other sources, only the activity and Task will be linked.

Open activities can be edited or rescheduled. Time, owner, contacts, address, activity details, and the linked Task deadline are kept synchronized. Completed and cancelled records remain immutable history. Cancelling an activity retains the record, cancellation reason, user, and time, and marks its linked Task `Cancelled`.

Submitting the activity Follow-up will save the feedback, mark the activity completed, complete the linked Task, save Completion Notes, and synchronize the relevant Lead/Pipeline Follow-up History when applicable.

## 7. Remote Engagement Activity Rules

Remote Engagement activities are created from Sales Lead/Pipeline Follow-up History or directly from the Sales Activities form. `Follow-up Notes` and `Next Steps / To-do` are separate activities.

### Follow-up Notes only

- Create one `Remote Engagement` activity with subtype `Follow-up`.
- Mark it `Completed` immediately.
- Do not create a pending Task.
- Synchronize the relevant Sales Lead and Pipeline Follow-up History.

### Next Steps / To-do only

- Create one separate `Remote Engagement` activity with subtype `Next Steps / To-do`.
- Create a linked Task.
- Mark the stored activity `Scheduled`.
- Display it as `Scheduled` before its due date, `Follow-up Required` with `Due Today` on the due date, and `Follow-up Required` with `Overdue` after the due date.
- The activity becomes `Completed` only when the linked Task is completed with required Completion Notes.

### Both fields

Create two separate Remote Engagement activities: one completed Follow-up activity and one pending Next Steps / To-do activity linked to the Task.

The new implementation will apply this rule only to newly created records. Existing Follow-up History will not be parsed or converted into historical Sales Activities.

## 8. Sales Lead Follow-up

Sales Leads will receive a Follow-up action using the existing Pipeline Follow-up vocabulary where applicable:

- Follow-up History.
- Follow-up Notes.
- Next Steps / To-do.
- To-do Due Date.

The same two-activity Remote Engagement rule will be applied. If the Lead has a linked Pipeline, synchronization will update both records without creating duplicate activities or Tasks.

## 9. Task Completion

The current click-on-status completion behavior will be removed.

- Status badges become display-only.
- `In Progress` and `Overdue` tasks receive a `Complete` button.
- Completion opens a dialog requiring `Completion Notes`.
- Completed Tasks display Completion Notes, Completed At, and Completed By.
- Reopening preserves the completion history and is logged.
- Completing an activity-linked Task updates the linked Sales Activity status.

## 10. Requirements Validation during Qualified Conversion

The existing Pipeline `Product` field is limited to 200 characters. Since Sales Lead `Requirements` is copied to Pipeline `Product`, changing a Lead to `Qualified` will be blocked when Requirements exceeds 200 characters.

The user will receive a clear message instructing them to keep the clear product/service requirement in Requirements, move communication history to `Note`, and confirm Qualified again. The system will not silently truncate content.

This validation will apply to form edits, quick updates, and API status changes.

## 11. Persistent Login

Flask-Login persistent sessions will be enabled with a recommended 30-day duration. Logout, password changes, and account deactivation will invalidate the session. Production cookies will use secure HttpOnly and SameSite settings.

## 12. Soft Delete and Archive

Sales Leads, Pipeline, Tasks, and Sales Activities will use soft deletion. Deleted records will be hidden from normal frontend lists while preserving:

- Deleted timestamp.
- Deleted user.
- Deleted entity ID and type.
- A JSON snapshot of the record.
- The audit log entry.

A `Deleted Records` archive table will preserve the snapshot independently of future schema changes.

## 13. Database Changes and Migration

The implementation will add:

- `sales_activities`.
- `sales_activity_contacts`.
- `deleted_records`.
- Sales Lead follow-up and soft-delete fields.
- Task activity/lead links, completion notes, completed metadata, and soft-delete fields.
- Pipeline soft-delete fields.
- Optional structured old/new audit values on ActivityLog.

The migration will be safe for the existing SQLite database and compatible with PostgreSQL. Historical Follow-up History will remain unchanged and will not be parsed.

## 14. Verification

After implementation, the following will be executed automatically:

- Database migration against the current database.
- Existing test suite.
- New tests for source validation, dual Remote Engagement activity creation, Task completion, synchronization, soft deletion, Requirements length validation, and persistent login.
- Flask application import and route registration checks.
- Template/build/static asset checks.
- A final database integrity check.
