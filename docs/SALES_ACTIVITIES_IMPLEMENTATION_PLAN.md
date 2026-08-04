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
- `Customer Visit`
- `DC Site Visit`
- `Remote Engagement Subtype`
- `Scheduled`, `Follow-up Required`, `Completed`, and `Cancelled`
- `Due Today` and `Overdue` reminder indicators
- `Existing Customer`
- `Event`
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

- `All`, `Customer Visit`, `DC Site Visit`, and `Remote Engagement` quick filters.
- Inclusive start/end date filtering. Remote Engagement uses Activity Date;
  Customer Visit and DC Site Visit use schedule overlap so cross-date visits are not omitted.
- Owner filtering for administrators.
- Summary statistics by source type.
- An administrator-only per-owner summary with mutually exclusive `Scheduled`,
  `Follow-up Required`, `Completed`, and `Cancelled` categories. `Due Today`
  and `Overdue` remain detailed reminders but are aggregated under
  `Follow-up Required` in this business-level summary.
- A month calendar with multi-date selection.
- A reverse-chronological activity table.
- An `Add Sales Activity` action.

The table will display:

- `Activity Date / Visit Date`.
- Visit start/end time for `Customer Visit` and `DC Site Visit`.
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

### Existing Customer, Event, and Other

These sources may use a manually entered Company. Existing Customer and Event may also offer fuzzy suggestions from existing CRM data, but manual entry remains allowed.

## 6. Scheduled Visits: Customer Visit and DC Site Visit

Both scheduled visit types support:

- `Customer Visit`: our salesperson visits the customer office, project site, event site, or another external location.
- `DC Site Visit`: the customer visits our Data Center for a tour, technical discussion, security review, or facility inspection.
- Source type and linked CRM record where applicable.
- Company, start/end date and time, repeatable contacts, detailed address, purpose/project, expected result, and remarks.

A planned Customer Visit or DC Site Visit creates one `Scheduled` Sales Activity and one linked Task. The Task due date uses the visit end date. Before the visit ends the activity remains `Scheduled`; immediately after the end time it displays `Follow-up Required`, and it becomes `Overdue` only if feedback is still missing 24 hours after the estimated end time. The linked Task follows the same grace-period rule.

Open activities can be edited or rescheduled. Time, owner, contacts, address, activity details, and the linked Task deadline remain synchronized. Completed and cancelled records remain immutable history. Cancelling an activity retains the record, reason, user, and time and cancels its linked Task.

Visit completion supports both operational entry points:

- Enter feedback in Sales Activities to complete the Activity and linked Task.
- Enter mandatory Completion Notes in Tasks to complete the Task and linked Activity.

In either path, feedback, status, completion time, and completing user synchronize. The Tasks page displays the Activity Type and may offer an `Open Sales Activity` detail shortcut, but users are not required to leave Tasks to complete a Visit.

## 7. Typed Follow-up and Next-Step Rules

Sales Lead and Pipeline `Add Follow-up` treat the two input areas independently:

### Follow-up Notes (completed activity)

- Follow-up Activity Type is required when notes are entered.
- The user independently selects `Customer Visit`, `DC Site Visit`, or `Remote Engagement`.
- A Visit requires actual start and end date/time; Remote Engagement uses Activity Date.
- Create one `Completed` Sales Activity with the notes saved as completion feedback.
- Do not create a Task.

### Next Steps / To-do (planned activity)

- Next Step Activity Type is required when next-step text is entered and may differ from the Follow-up type.
- Remote Engagement requires To-do Due Date.
- Customer Visit and DC Site Visit require estimated start and end date/time.
- Create one `Scheduled` Sales Activity and one linked Task.
- For a Visit, the Task due date uses the visit end date; for Remote Engagement it uses To-do Due Date.

### Both fields

Create two separate activities: one completed Follow-up activity without a Task and one scheduled Next-Step activity with a linked Task. If a Lead and Pipeline are already associated, the new Activity and Task store both links and update both Follow-up Histories without creating duplicates.

The synchronization logic applies only to newly saved records with an explicit activity type. Existing Follow-up History is never parsed, guessed, or backfilled, and legacy Tasks without a Sales Activity link continue to work unchanged.

## 8. Direct Sales Activities Entry

The standalone Sales Activities form continues to support all three activity types. It is the primary location for full activity detail, rescheduling, cancellation, contacts, address, purpose/project, expected result, and remarks. Activity records created from Leads or Pipeline appear in the same Activity List and statistics, so reporting remains unified regardless of where the user entered the new activity.

For Source Type `Sales Leads` or `Pipeline`, the selected CRM record is required and linked IDs are stored. When the Lead and Pipeline are already related, both links are retained. Historical records are not altered.

## 9. Task Completion and Reopening

- Status badges are display-only; open Tasks use the `Complete` action.
- Completion always requires non-empty `Completion Notes`, including Customer Visit and DC Site Visit Tasks.
- Completing an activity-linked Task synchronizes its Sales Activity status, completion notes, completion timestamp, and completing user.
- The completion result is appended to every linked Lead/Pipeline Follow-up History once.
- Completing a Visit from Sales Activities synchronizes the linked Task.
- Reopening a completed Task reopens the linked Sales Activity and clears current completion metadata while preserving audit logging.
- Legacy Tasks without `sales_activity_id` remain completable and are not forced into Sales Activities.

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

The migration will be safe for the existing SQLite database and compatible with PostgreSQL. Legacy activity names (`Online`, `Field Visit`, `On-site Visit`, and the interim `Out of Building Visit`) will be migrated to the current canonical names without losing linked records or generated history text. Historical Follow-up History will remain unchanged and will not be parsed.

## 14. Verification

After implementation, the following will be executed automatically:

- Database migration against the current database.
- Existing test suite.
- New tests for source validation, dual Remote Engagement activity creation, Task completion, synchronization, soft deletion, Requirements length validation, and persistent login.
- Flask application import and route registration checks.
- Template/build/static asset checks.
- A final database integrity check.
