import {renderDomain, domainTitles} from './domains.js';
const config = await (await fetch('/config.json')).json();
const titles = {littlex: 'LittleX', jacord: 'Jacord', jdrive: 'JDrive', issue_desk: 'IssueDesk', approval_desk: 'ApprovalDesk', stock_room: 'StockRoom', clinic_queue: 'ClinicQueue', course_path: 'CoursePath', library_loans: 'LibraryLoans', event_seats: 'EventSeats', help_queue: 'HelpQueue'};
document.title = `${titles[config.app] || domainTitles[config.app] || config.app} | TTG Application Suite`;
document.querySelector('#title').textContent = titles[config.app] || domainTitles[config.app] || config.app;
const workspace = document.querySelector('#workspace');
const notice = document.querySelector('#notice');
let token = '', activeChannel = '', activeFolder = '', replyTarget = '';
const folderHistory = [];
const uiEvents = [];
window.suiteEvents = uiEvents;

function element(tag, text, attributes = {}) {
  const item = document.createElement(tag);
  if (text !== null) item.textContent = text;
  for (const [key, value] of Object.entries(attributes)) item.setAttribute(key, value);
  return item;
}
function message(text, error = false) { notice.textContent = text; notice.className = error ? 'error' : ''; }
function button(text, action, attributes = {}) {
  const item = element('button', text, {type: 'button', ...attributes});
  item.addEventListener('click', () => perform(action));
  return item;
}
async function perform(action) {
  try { await action(); } catch (error) { message(error.message, true); }
}
async function request(path, body) {
  const response = await fetch('/api' + path, {method: 'POST',
    headers: {'Content-Type': 'application/json', ...(token ? {Authorization: 'Bearer ' + token} : {})},
    body: JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok || result.ok === false || result.error) throw new Error(result.error?.message || 'Request failed');
  return result.data || result;
}
async function walker(name, body = {}, target = '') {
  const result = await request('/walker/' + name + (target ? '/' + target : ''), body);
  if (result.diagnostics?.length) throw new Error('The action could not be completed with the current permissions');
  return result.reports;
}
function form(fields, submitLabel, action) {
  const item = element('form', null);
  for (const [name, label, type = 'text'] of fields) {
    const wrapper = element('label', label);
    wrapper.append(element('input', null, {name, type, required: ''}));
    item.append(wrapper);
  }
  item.append(element('button', submitLabel));
  item.addEventListener('submit', event => {event.preventDefault(); perform(async () => {
    const values = Object.fromEntries(new FormData(item));
    if (fields.some(([name]) => !String(values[name]).trim())) throw new Error('Please enter a nonempty value');
    await action(values); item.reset();
  });});
  return item;
}
document.querySelector('#login').addEventListener('submit', event => {
  event.preventDefault();
  perform(async () => {
    const data = Object.fromEntries(new FormData(event.currentTarget));
    const result = await request('/user/login', {identity: {type: 'username', value: data.username},
      credential: {type: 'password', password: data.password}});
    token = result.token;
    document.querySelector('#auth').hidden = true; workspace.hidden = false;
    await refresh(); message('Signed in');
  });
});
async function refresh() {
  if (config.app === 'littlex') await littlex();
  else if (config.app === 'jacord') await jacord();
  else if (config.app === 'jdrive') await jdrive();
  else if (config.app === 'issue_desk') await issueDesk();
  else if (config.app === 'approval_desk') await approvalDesk();
  else if (config.app === 'stock_room') await stockRoom();
  else if (config.app === 'clinic_queue') await clinicQueue();
  else if (config.app === 'course_path') await coursePath();
  else if (config.app === 'library_loans') await libraryLoans();
  else if (config.app === 'event_seats') await eventSeats();
  else if (config.app === 'help_queue') await helpQueue();
  else await renderDomain(config.app, {walker, workspace, element, button, form, message, uiEvents});
}

async function littlex(query = '') {
  const profile = (await walker('get_profile'))[0];
  const feed = (await walker('load_feed', {search_query: query}))[0];
  const profiles = (await walker('get_all_profiles'))[0];
  workspace.replaceChildren(element('h2', 'Home feed'));
  workspace.append(form([['content', 'Post content']], 'Publish post', async ({content}) => {
    const created = (await walker('create_tweet', {content}))[0];
    uiEvents.push({action: 'create_tweet', id: created.id, content});
    await littlex(); message('Post published');
  }));
  workspace.append(form([['query', 'Search posts']], 'Search', async ({query}) => {
    await littlex(query); message('Search results updated');
  }));
  const people = element('section', null, {'data-testid': 'people'});
  people.append(element('h3', 'People'));
  const following = new Set(profile.following.map(person => person.id));
  for (const person of profiles.filter(person => person.id !== profile.id)) {
    const row = element('div', null, {class: 'row', 'data-id': person.id});
    row.append(element('span', person.username));
    row.append(button(following.has(person.id) ? 'Unfollow' : 'Follow', async () => {
      const followed = !following.has(person.id);
      await walker(followed ? 'follow_user' : 'unfollow_user', {target_id: person.id});
      uiEvents.push({action: followed ? 'follow' : 'unfollow', id: person.id});
      await littlex(); message(followed ? 'Following updated' : 'Follow removed');
    })); people.append(row);
  }
  workspace.append(people);
  const posts = element('section', null, {'data-testid': 'feed'});
  for (const post of feed) {
    const card = element('article', null, {'data-id': post.id});
    card.append(element('small', post.author_username), element('p', post.content));
    card.append(button(`${post.likes.includes(profile.username) ? 'Unlike' : 'Like'} (${post.likes.length})`, async () => {
      const result = (await walker('like_tweet', {tweet_id: post.id}))[0];
      uiEvents.push({action: 'like', id: post.id, likes: result.likes});
      await littlex(); message(result.liked ? 'Post liked' : 'Like removed');
    })); posts.append(card);
  }
  workspace.append(posts);
}

async function jacord() {
  const groups = (await walker('ListWorkspaces'))[0];
  workspace.replaceChildren(element('h2', 'Workspaces'));
  const navigation = element('nav', null);
  const channels = [];
  for (const group of groups) channels.push(...(await walker('ListChannels', {workspace_id: group.id}))[0]);
  activeChannel ||= channels[0]?.id;
  for (const channel of channels) navigation.append(button('# ' + channel.name, async () => {
    activeChannel = channel.id; replyTarget = ''; await jacord(); message('Channel opened');
  }, {'data-id': channel.id}));
  workspace.append(navigation);
  if (!activeChannel) return;
  const channel = channels.find(channel => channel.id === activeChannel);
  workspace.append(element('h3', '# ' + channel.name));
  workspace.append(form([['content', replyTarget ? 'Reply content' : 'Message content']],
    replyTarget ? 'Send reply' : 'Send message', async ({content}) => {
      const parent = replyTarget;
      const id = (await walker(parent ? 'PostReply' : 'PostMessage', parent ?
        {parent_message_id: parent, content} : {channel_id: activeChannel, content}))[0];
      uiEvents.push({action: parent ? 'post_reply' : 'post_message', id, content,
        parent, channel: activeChannel}); replyTarget = ''; await jacord(); message('Message sent');
    }));
  const messages = element('section', null, {'data-testid': 'messages'});
  for (const item of await walker('load_channel', {}, activeChannel)) {
    const card = element('article', null, {'data-id': item.id});
    card.append(element('small', item.author_username), element('p', item.content),
      button('Reply', async () => {replyTarget = item.id; await jacord(); message('Reply selected');}));
    messages.append(card);
  }
  workspace.append(messages);
}

async function jdrive() {
  if (!activeFolder) activeFolder = (await walker('GetRoot'))[0].id;
  const folder = (await walker('ListFolder', {}, activeFolder))[0];
  workspace.replaceChildren(element('h2', folder.name));
  workspace.append(button('Back to parent', async () => {
    if (folderHistory.length) activeFolder = folderHistory.pop(); await jdrive();
  }));
  workspace.append(form([['name', 'Folder name']], 'Create folder', async ({name}) => {
    const created = (await walker('NewFolder', {name}, activeFolder))[0];
    uiEvents.push({action: 'mkdir', id: created.id, parent: activeFolder, name});
    await jdrive(); message('Folder created');
  }));
  workspace.append(button('Show visible folder tree', async () => {
    const tree = (await walker('VisibleFolderTree', {}, activeFolder))[0];
    const listing = element('section', null, {'data-testid': 'tree'});
    for (const entry of tree.entries) listing.append(element('p', entry.path));
    workspace.querySelector('[data-testid="tree"]')?.remove(); workspace.append(listing);
    message('Visible folder tree loaded');
  }));
  const entries = element('section', null, {'data-testid': 'entries'});
  for (const entry of folder.entries) {
    const row = element('article', null, {'data-id': entry.id, class: 'row'});
    row.append(element('span', entry.name), element('small', entry.kind));
    if (entry.kind === 'folder') {
      row.append(button('Open', async () => {
        folderHistory.push(activeFolder); activeFolder = entry.id; await jdrive(); message('Folder opened');
      }), button('Move to trash', async () => {
        await walker('TrashFolder', {}, entry.id);
        uiEvents.push({action: 'trash', id: entry.id}); await jdrive(); message('Folder moved to trash');
      }));
    } else {
      row.append(button('Download', async () => {
        const file = (await walker('Download', {}, entry.id))[0];
        const bytes = Uint8Array.from(atob(file.content_b64), character => character.charCodeAt(0));
        const url = URL.createObjectURL(new Blob([bytes], {type: file.mime}));
        const link = element('a', file.name, {href: url, download: file.name}); link.click(); URL.revokeObjectURL(url);
        uiEvents.push({action: 'download', id: entry.id, size: bytes.length});
        message(`Downloaded ${file.name} (${bytes.length} bytes)`);
      }));
    }
    entries.append(row);
  }
  workspace.append(entries);
}

async function issueDesk() {
  const board = (await walker('ProjectBoard'))[0];
  workspace.replaceChildren(element('h2', board.projects[0]?.name || 'No project available'));
  if (!board.projects.length) return;
  async function mutation(name, body, success) {
    const result = (await walker(name, body))[0];
    if (!result.ok) throw new Error(result.error);
    uiEvents.push({action: name, ...body, result});
    await issueDesk(); message(success);
  }
  workspace.append(form([['title', 'Issue title'], ['priority', 'Priority (1 to 5)', 'number']],
    'Create issue', async ({title, priority}) => mutation('CreateIssue',
      {project_id: board.projects[0].id, title, priority: Number(priority)}, 'Issue created')));
  const issues = element('div', null, {class: 'grid', 'data-testid': 'issues'});
  for (const issue of board.issues) {
    const card = element('article', null, {'data-id': issue.id});
    card.append(element('h3', issue.title), element('span', issue.status, {class: 'tag'}),
      element('p', `Priority ${issue.priority}; assigned to ${issue.assignees.map(person => person.name).join(', ') || 'nobody'}`));
    const blocked = issue.blockers.filter(item => item.status !== 'closed');
    card.append(element('p', blocked.length ? 'Blocked by: ' + blocked.map(item => item.title).join(', ') : 'No open blockers'));
    const assignments = element('label', 'Assign engineer');
    const engineer = element('select', null, {'aria-label': 'Assign engineer'});
    for (const person of board.engineers) engineer.append(element('option', person.name, {value: person.id}));
    assignments.append(engineer); card.append(assignments, button('Assign', async () =>
      mutation('AssignIssue', {issue_id: issue.id, engineer_id: engineer.value}, 'Assignment saved')));
    for (const comment of [...issue.comments].sort((a,b) => a.sequence - b.sequence))
      card.append(element('p', `${comment.sequence}. ${comment.body}`));
    card.append(form([['body', 'Comment']], 'Add comment', async ({body}) =>
      mutation('CommentIssue', {issue_id: issue.id, body}, 'Comment added')));
    const dependencies = element('label', 'Blocking issue');
    const blocker = element('select', null, {'aria-label': 'Blocking issue'});
    for (const item of board.issues.filter(item => item.id !== issue.id))
      blocker.append(element('option', item.title, {value: item.id}));
    dependencies.append(blocker);
    card.append(dependencies, button('Add blocker', async () =>
      mutation('BlockIssue', {issue_id: issue.id, blocker_id: blocker.value}, 'Blocker added')));
    card.append(button(issue.status === 'closed' ? 'Reopen issue' : 'Close issue', async () =>
      mutation(issue.status === 'closed' ? 'ReopenIssue' : 'CloseIssue', {issue_id: issue.id},
        issue.status === 'closed' ? 'Issue reopened' : 'Issue closed')));
    issues.append(card);
  }
  workspace.append(issues);
}

async function approvalDesk() {
  const board = (await walker('ExpenseBoard'))[0];
  workspace.replaceChildren(element('h2', 'Expenses and approvals'));
  async function mutation(name, body, text) {
    const result = (await walker(name, body))[0];
    if (!result.ok) throw new Error(result.error);
    uiEvents.push({action: name, ...body, result}); await approvalDesk(); message(text);
  }
  workspace.append(form([['title', 'Expense title']], 'Create expense', async ({title}) =>
    mutation('CreateExpense', {title}, 'Expense created')));
  const expenses = element('div', null, {'data-testid': 'expenses'});
  for (const expense of board.expenses) {
    const card = element('article', null, {'data-id': expense.id});
    card.append(element('h3', expense.title), element('span', expense.status, {class: 'tag'}),
      element('p', `Submitted amount: ${expense.total_cents} cents`));
    for (const line of expense.lines) card.append(element('p', `${line.description}: ${line.quantity} × ${line.unit_cents} cents`));
    if (expense.status === 'draft') {
      card.append(form([['description', 'Line description'], ['quantity', 'Quantity', 'number'], ['unit_cents', 'Unit price (cents)', 'number']],
        'Add line item', async ({description, quantity, unit_cents}) => mutation('AddLineItem',
          {expense_id: expense.id, description, quantity: Number(quantity), unit_cents: Number(unit_cents)}, 'Line item added')));
      card.append(button('Submit expense', async () => mutation('SubmitExpense', {expense_id: expense.id}, 'Expense submitted')));
    }
    for (const step of expense.steps) {
      const row = element('div', null, {class: 'row'});
      row.append(element('span', `Step ${step.position}: ${step.approver} (${step.role}) — ${step.decision}`));
      if (expense.status === 'submitted' && step.decision === 'pending') row.append(
        button(`Approve step ${step.position}`, async () => mutation('DecideApproval', {step_id: step.id, approve: true}, 'Approval recorded')),
        button(`Reject step ${step.position}`, async () => mutation('DecideApproval', {step_id: step.id, approve: false}, 'Expense rejected')));
      card.append(row);
    }
    if (expense.status === 'approved') card.append(button('Pay expense', async () =>
      mutation('PayExpense', {expense_id: expense.id}, 'Expense paid')));
    for (const payment of expense.payments) card.append(element('p', `Payment ${payment.reference}: ${payment.amount_cents} cents`));
    expenses.append(card);
  }
  workspace.append(expenses);
}

async function stockRoom() {
  const inventory = (await walker('Inventory'))[0];
  workspace.replaceChildren(element('h2', inventory.warehouses[0]?.name || 'No warehouse available'));
  async function mutation(name, body, text) {
    const result = (await walker(name, body))[0];
    if (!result.ok) throw new Error(result.error);
    uiEvents.push({action: name, ...body, result}); await stockRoom(); message(text);
  }
  const receipt = form([['quantity', 'Receipt quantity', 'number']], 'Receive stock', async ({quantity, sku_id}) =>
    mutation('ReceiveStock', {sku_id, quantity: Number(quantity)}, 'Stock received'));
  const order = form([['reference', 'Order reference'], ['quantity', 'Reservation quantity', 'number']], 'Reserve stock',
    async ({reference, quantity, sku_id}) => mutation('ReserveStock', {sku_id, reference, quantity: Number(quantity)}, 'Stock reserved'));
  for (const [formElement, label] of [[receipt, 'Receipt SKU'], [order, 'Reservation SKU']]) {
    const wrapper = element('label', label);
    const select = element('select', null, {name: 'sku_id', 'aria-label': label});
    for (const sku of inventory.skus) select.append(element('option', `${sku.name} (${sku.code})`, {value: sku.id}));
    wrapper.append(select); formElement.prepend(wrapper);
  }
  workspace.append(receipt, order);
  const totals = element('section', null, {'data-testid': 'stock-totals'});
  for (const sku of inventory.skus) {
    const lots = inventory.lots.filter(lot => lot.sku_id === sku.id);
    const available = lots.reduce((sum, lot) => sum + lot.available, 0);
    const received = lots.reduce((sum, lot) => sum + lot.received, 0);
    const dispatched = lots.reduce((sum, lot) => sum + lot.dispatched, 0);
    const card = element('article', null, {'data-id': sku.id});
    card.append(element('h3', sku.name), element('p', `Received ${received}; available ${available}; reserved ${received - available - dispatched}; dispatched ${dispatched}`));
    for (const lot of lots) card.append(element('small', `Lot ${lot.sequence}: ${lot.available} available. `));
    totals.append(card);
  }
  workspace.append(totals);
  const reservations = element('section', null, {'data-testid': 'reservations'});
  reservations.append(element('h3', 'Reservations'));
  for (const reservation of inventory.reservations) {
    const card = element('article', null, {'data-id': reservation.id});
    card.append(element('h3', reservation.reference), element('span', reservation.status, {class: 'tag'}),
      element('p', `${reservation.quantity} units; lots: ${reservation.allocations.map(item => `${item.sequence} (${item.quantity})`).join(', ')}`));
    if (reservation.status === 'reserved') card.append(
      button('Release reservation', async () => mutation('ReleaseReservation', {reservation_id: reservation.id}, 'Reservation released')),
      button('Dispatch reservation', async () => mutation('DispatchReservation', {reservation_id: reservation.id}, 'Reservation dispatched')));
    reservations.append(card);
  }
  workspace.append(reservations);
}

async function clinicQueue() {
  const schedule = (await walker('ClinicSchedule'))[0];
  workspace.replaceChildren(element('h2', `${schedule.clinics[0]?.name || 'Clinic'} — ${schedule.clinics[0]?.date || ''}`));
  async function mutation(name, body, text) {
    const result = (await walker(name, body))[0];
    if (!result.ok) throw new Error(result.error);
    uiEvents.push({action: name, ...body, result}); await clinicQueue(); message(text);
  }
  const time = minutes => `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
  const create = form([['start', 'Start time', 'time'], ['duration', 'Duration (minutes)', 'number']], 'Add schedule slot',
    async ({practitioner_id, start, duration}) => {
      const [hour, minute] = start.split(':').map(Number);
      await mutation('AddSlot', {practitioner_id, start_minute: hour * 60 + minute, duration: Number(duration)}, 'Schedule slot added');
    });
  const personLabel = element('label', 'Practitioner');
  const people = element('select', null, {name: 'practitioner_id', 'aria-label': 'Practitioner'});
  for (const person of schedule.practitioners) people.append(element('option', person.name, {value: person.id}));
  personLabel.append(people); create.prepend(personLabel); workspace.append(create);
  const slots = element('div', null, {'data-testid': 'slots', class: 'grid'});
  for (const slot of schedule.slots) {
    const person = schedule.practitioners.find(person => person.id === slot.practitioner_id);
    const card = element('article', null, {'data-id': slot.id});
    card.append(element('h3', `${person.name} ${time(slot.start_minute)}`), element('small', `${slot.duration} minutes; ${person.specialty}`));
    for (const appointment of slot.appointments) {
      const row = element('div', null, {class: 'row'});
      row.append(element('span', `${appointment.patient} — ${appointment.status}`));
      if (appointment.status === 'booked') row.append(button('Cancel appointment', async () =>
        mutation('CancelAppointment', {appointment_id: appointment.id}, 'Appointment cancelled')));
      card.append(row);
    }
    if (!slot.appointments.some(appointment => appointment.status === 'booked'))
      card.append(form([['patient', 'Patient name']], 'Book appointment', async ({patient}) =>
        mutation('BookAppointment', {slot_id: slot.id, patient}, 'Appointment booked')));
    slots.append(card);
  }
  workspace.append(slots);
}

async function coursePath() {
  const dashboard = (await walker('LearningDashboard'))[0];
  workspace.replaceChildren(element('h2', 'Courses and learner progress'));
  async function mutation(name, body, text) {
    const result = (await walker(name, body))[0];
    if (!result.ok) throw new Error(result.error);
    uiEvents.push({action: name, ...body, result}); await coursePath(); message(text);
  }
  for (const course of dashboard.courses) {
    const section = element('section', null);
    section.append(element('h3', course.title));
    section.append(form([['learner', 'Learner name']], 'Enroll learner', async ({learner}) =>
      mutation('Enroll', {course_id: course.id, learner}, 'Learner enrolled')));
    const learners = dashboard.enrollments.filter(item => item.course_id === course.id);
    for (const enrollment of learners) {
      const card = element('article', null, {'data-testid': 'enrollment', 'data-id': enrollment.id});
      card.append(element('h3', enrollment.learner), element('p', `${enrollment.completed.length} of ${enrollment.total_lessons} lessons completed`));
      const completed = new Set(enrollment.completed.map(item => item.lesson_id));
      for (const module of [...course.modules].sort((a,b) => a.position - b.position)) {
        card.append(element('h4', module.title));
        for (const lesson of [...module.lessons].sort((a,b) => a.position - b.position)) {
          const row = element('div', null, {class: 'row', 'data-lesson-id': lesson.id});
          const locked = lesson.requires.some(id => !completed.has(id));
          row.append(element('span', `${lesson.title} (${lesson.minutes} minutes)`),
            element('small', completed.has(lesson.id) ? 'Completed' : locked ? 'Prerequisites required' : 'Available'));
          if (!completed.has(lesson.id)) row.append(button('Complete ' + lesson.title, async () =>
            mutation('CompleteLesson', {enrollment_id: enrollment.id, lesson_id: lesson.id}, 'Lesson completed')));
          card.append(row);
        }
      }
      section.append(card);
    }
    const authoring = form([['title', 'Lesson title'], ['minutes', 'Lesson duration (minutes)', 'number']], 'Add lesson',
      async ({title, minutes, module_id, prerequisite_id}) => mutation('AddLesson',
        {title, minutes: Number(minutes), module_id, prerequisite_id}, 'Lesson added'));
    const moduleLabel = element('label', 'Module');
    const modules = element('select', null, {name: 'module_id', 'aria-label': 'Module'});
    for (const module of course.modules) modules.append(element('option', module.title, {value: module.id}));
    moduleLabel.append(modules);
    const prerequisiteLabel = element('label', 'Prerequisite');
    const prerequisites = element('select', null, {name: 'prerequisite_id', 'aria-label': 'Prerequisite'});
    prerequisites.append(element('option', 'No prerequisite', {value: ''}));
    for (const module of course.modules) for (const lesson of module.lessons)
      prerequisites.append(element('option', lesson.title, {value: lesson.id}));
    prerequisiteLabel.append(prerequisites); authoring.prepend(moduleLabel, prerequisiteLabel);
    section.append(authoring); workspace.append(section);
  }
}

async function libraryLoans() {
  const catalog = (await walker('LibraryCatalog'))[0];
  workspace.replaceChildren(element('h2', catalog.libraries[0]?.name || 'Library'));
  async function mutation(name, body, text) {
    const result = (await walker(name, body))[0];
    if (!result.ok) throw new Error(result.error);
    uiEvents.push({action: name, ...body, result}); await libraryLoans(); message(text);
  }
  const titles = element('div', null, {class: 'grid', 'data-testid': 'titles'});
  for (const title of catalog.titles) {
    const card = element('article', null, {'data-id': title.id});
    card.append(element('h3', title.name), element('small', title.edition),
      element('p', `${title.copies.filter(copy => copy.available).length} of ${title.copies.length} copies available`));
    const label = element('label', 'Patron');
    const patron = element('select', null, {'aria-label': 'Patron'});
    for (const item of catalog.patrons) patron.append(element('option', item.name, {value: item.id}));
    label.append(patron); card.append(label,
      button('Borrow title', async () => mutation('BorrowTitle', {title_id: title.id, patron_id: patron.value}, 'Title borrowed')),
      button('Place hold', async () => mutation('PlaceHold', {title_id: title.id, patron_id: patron.value}, 'Hold queued')));
    for (const hold of [...title.holds].sort((a,b) => a.position - b.position)) {
      const row = element('div', null, {class: 'row'});
      row.append(element('span', `Hold ${hold.position}: ${hold.patron} — ${hold.status}`));
      if (hold.status === 'queued') row.append(button('Cancel hold', async () => mutation('CancelHold', {hold_id: hold.id}, 'Hold cancelled')));
      card.append(row);
    }
    titles.append(card);
  }
  workspace.append(titles, element('h3', 'Loans'));
  const loans = element('section', null, {'data-testid': 'loans'});
  for (const loan of catalog.loans) {
    const card = element('article', null, {'data-id': loan.id});
    card.append(element('h3', `${loan.title} — ${loan.patron}`), element('span', loan.status, {class: 'tag'}));
    if (loan.status === 'active') card.append(button('Return loan', async () => mutation('ReturnLoan', {loan_id: loan.id}, 'Loan returned; hold queue processed')));
    loans.append(card);
  }
  workspace.append(loans);
}

async function eventSeats() {
  const catalog = (await walker('EventCatalog'))[0];
  workspace.replaceChildren(element('h2', catalog.venues[0]?.name || 'Events'));
  async function mutation(name, body, text) {
    const result = (await walker(name, body))[0];
    if (!result.ok) throw new Error(result.error);
    uiEvents.push({action: name, ...body, result}); await eventSeats(); message(text);
  }
  for (const event of catalog.events) {
    const selected = new Set();
    const card = element('section', null, {'data-testid': 'event', 'data-id': event.id});
    card.append(element('h3', event.title));
    for (const section of event.sections) {
      card.append(element('h4', section.name));
      const seats = element('div', null, {class: 'row'});
      for (const seat of section.seats) {
        const label = element('label', `${seat.label}: ${seat.price_cents} cents; ${seat.status}`);
        const input = element('input', null, {type: 'checkbox', 'aria-label': 'Seat ' + seat.label});
        input.disabled = seat.status !== 'available';
        input.addEventListener('change', () => input.checked ? selected.add(seat.id) : selected.delete(seat.id));
        label.prepend(input); seats.append(label);
      }
      card.append(seats);
    }
    card.append(form([['reference', 'Booking reference']], 'Hold selected seats', async ({reference}) =>
      mutation('HoldSeats', {event_id: event.id, reference, seat_ids: [...selected]}, 'Seats held')));
    for (const booking of event.bookings) {
      const item = element('article', null, {'data-testid': 'booking', 'data-id': booking.id});
      item.append(element('h4', booking.reference), element('span', booking.status, {class: 'tag'}),
        element('p', `${booking.seat_ids.length} seats; total ${booking.total_cents} cents`));
      if (booking.status === 'held') item.append(button('Confirm booking', async () => mutation('ConfirmBooking', {booking_id: booking.id}, 'Booking confirmed')));
      if (booking.status !== 'cancelled') item.append(button('Cancel booking', async () => mutation('CancelBooking', {booking_id: booking.id}, 'Booking cancelled')));
      for (const refund of booking.refunds) item.append(element('p', `Refund: ${refund.amount_cents} cents`));
      card.append(item);
    }
    workspace.append(card);
  }
}

async function helpQueue() {
  const board = (await walker('DeskBoard'))[0];
  workspace.replaceChildren(element('h2', board.desks[0]?.name || 'Help desk'));
  if (!board.desks.length) return;
  async function mutation(name, body, text) {
    const result = (await walker(name, body))[0];
    if (!result.ok) throw new Error(result.error);
    uiEvents.push({action: name, ...body, result}); await helpQueue(); message(text);
  }
  workspace.append(element('p', `Simulation clock: minute ${board.desks[0].tick}. Urgent response: 30 minutes; normal response: 120 minutes.`));
  workspace.append(form([['minutes', 'Advance minutes', 'number']], 'Advance clock', async ({minutes}) =>
    mutation('AdvanceClock', {minutes: Number(minutes)}, 'Clock advanced')),
    button('Evaluate SLA', async () => mutation('EvaluateSLA', {}, 'SLA evaluated')));
  const create = form([['subject', 'Ticket subject']], 'Open ticket', async ({subject, customer_id, priority}) =>
    mutation('CreateTicket', {subject, customer_id, priority}, 'Ticket opened'));
  const customerLabel = element('label', 'Customer');
  const customers = element('select', null, {name: 'customer_id', 'aria-label': 'Customer'});
  for (const customer of board.customers) customers.append(element('option', customer.name, {value: customer.id}));
  customerLabel.append(customers);
  const priorityLabel = element('label', 'Priority');
  const priority = element('select', null, {name: 'priority', 'aria-label': 'Priority'});
  for (const name of ['normal', 'urgent']) priority.append(element('option', name, {value: name}));
  priorityLabel.append(priority); create.prepend(customerLabel, priorityLabel); workspace.append(create);
  const tickets = element('div', null, {'data-testid': 'tickets', class: 'grid'});
  for (const ticket of board.tickets) {
    const card = element('article', null, {'data-id': ticket.id});
    card.append(element('h3', ticket.subject), element('span', ticket.status, {class: 'tag'}),
      element('p', `${ticket.customer}; ${ticket.priority}; opened at minute ${ticket.opened_tick}`),
      element('p', `Assigned: ${ticket.agents.map(agent => agent.name).join(', ') || 'nobody'}; ${ticket.escalated ? 'Escalated' : 'Within SLA'}`));
    for (const reply of ticket.replies) card.append(element('p', `Minute ${reply.tick}: ${reply.body}`));
    if (ticket.status === 'open') {
      const label = element('label', 'Assigned agent');
      const agents = element('select', null, {'aria-label': 'Assigned agent'});
      for (const agent of board.agents) agents.append(element('option', `${agent.name} (tier ${agent.tier})`, {value: agent.id}));
      label.append(agents); card.append(label, button('Assign agent', async () =>
        mutation('AssignTicket', {ticket_id: ticket.id, agent_id: agents.value}, 'Agent assigned')));
      card.append(form([['body', 'Reply message']], 'Send reply', async ({body}) =>
        mutation('ReplyTicket', {ticket_id: ticket.id, body}, 'Reply sent')),
        button('Resolve ticket', async () => mutation('ResolveTicket', {ticket_id: ticket.id}, 'Ticket resolved')));
    }
    tickets.append(card);
  }
  workspace.append(tickets);
}
