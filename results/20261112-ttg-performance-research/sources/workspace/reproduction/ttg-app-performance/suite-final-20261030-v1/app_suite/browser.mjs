import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
import {runAdditional} from './additional_browser.mjs';
const require = createRequire(import.meta.url);
const {chromium} = require(process.env.TTG_PLAYWRIGHT_MODULE || '/tmp/ttg-suite-browser/node_modules/playwright');
const [app, url, directory] = process.argv.slice(2);
const browser = await chromium.launch({headless: true, args: ['--no-sandbox']});
const context = await browser.newContext({viewport: {width: 1280, height: 960}, recordVideo: undefined});
await context.tracing.start({screenshots: true, snapshots: true, sources: true});
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
async function status(text) {
  await page.waitForFunction(text => document.querySelector('#notice').textContent === text, text);
}
try {
  await page.goto(url);
  await page.getByLabel('Password', {exact: true}).fill('isolated-suite-seed-password');
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await status('Signed in');
  if (app === 'littlex') {
    await page.getByLabel('Post content', {exact: true}).fill('Browser verification post #suite');
    await page.getByRole('button', {name: 'Publish post', exact: true}).click();
    await status('Post published');
    const post = page.locator('[data-testid="feed"] article').filter({hasText: 'Browser verification post #suite'});
    assert.equal(await post.count(), 1);
    await post.getByRole('button', {name: /^Like/}).click();
    await status('Post liked');
    await page.getByLabel('Search posts', {exact: true}).fill('Browser verification post');
    await page.getByRole('button', {name: 'Search', exact: true}).click();
    await status('Search results updated');
    assert.equal(await page.locator('[data-testid="feed"] article').count(), 1);
    assert.match(await post.textContent(), /Unlike \(1\)/);
  } else if (app === 'jacord') {
    await page.locator('[data-testid="messages"] article').first().getByRole('button', {name: 'Reply', exact: true}).click();
    await status('Reply selected');
    await page.getByLabel('Reply content', {exact: true}).fill('Browser verification reply');
    await page.getByRole('button', {name: 'Send reply', exact: true}).click();
    await status('Message sent');
    assert.equal(await page.locator('[data-testid="messages"] article').filter({hasText: 'Browser verification reply'}).count(), 1);
    const channels = page.locator('nav button');
    await channels.nth(1).click(); await status('Channel opened');
    assert.equal(await page.locator('[data-testid="messages"] article').filter({hasText: 'Browser verification reply'}).count(), 0);
    await channels.first().click();
    await page.locator('[data-testid="messages"] article').filter({hasText: 'Browser verification reply'}).waitFor();
  } else if (app === 'jdrive') {
    await page.getByLabel('Folder name', {exact: true}).fill('Browser verification folder');
    await page.getByRole('button', {name: 'Create folder', exact: true}).click();
    await status('Folder created');
    const created = page.locator('[data-testid="entries"] article').filter({hasText: 'Browser verification folder'});
    await created.getByRole('button', {name: 'Open', exact: true}).click(); await status('Folder opened');
    assert.equal(await page.locator('[data-testid="entries"] article').count(), 0);
    await page.getByRole('button', {name: 'Back to parent', exact: true}).click();
    await created.waitFor();
    const existing = page.locator('[data-testid="entries"] article').filter({hasText: 'new-folder'});
    await existing.getByRole('button', {name: 'Move to trash', exact: true}).click(); await status('Folder moved to trash');
    assert.equal(await existing.count(), 0);
    await page.getByRole('button', {name: 'Show visible folder tree', exact: true}).click(); await status('Visible folder tree loaded');
    assert.match(await page.locator('[data-testid="tree"]').textContent(), /Browser verification folder/);
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', {name: 'Download', exact: true}).click();
    const download = await downloadPromise;
    await download.saveAs(directory + '/browser-download.txt');
    const expectedFile = Buffer.from('TTG corpus file content. '.repeat(3)).subarray(0, 64);
    assert.deepEqual(await fs.readFile(directory + '/browser-download.txt'), expectedFile);
  } else if (app === 'issue_desk') {
    await page.getByLabel('Issue title', {exact: true}).fill('Browser release checklist');
    await page.getByLabel('Priority (1 to 5)', {exact: true}).fill('1');
    await page.getByRole('button', {name: 'Create issue', exact: true}).click(); await status('Issue created');
    const issue = page.locator('[data-testid="issues"] article').filter({has: page.getByRole('heading', {name: 'Browser release checklist', exact: true})});
    await issue.getByLabel('Assign engineer', {exact: true}).selectOption({label: 'Morgan'});
    await issue.getByRole('button', {name: 'Assign', exact: true}).click(); await status('Assignment saved');
    await issue.getByLabel('Comment', {exact: true}).fill('Reviewed in browser');
    await issue.getByRole('button', {name: 'Add comment', exact: true}).click(); await status('Comment added');
    await issue.getByLabel('Blocking issue', {exact: true}).selectOption({label: 'Implement parser fix'});
    await issue.getByRole('button', {name: 'Add blocker', exact: true}).click(); await status('Blocker added');
    await issue.getByRole('button', {name: 'Close issue', exact: true}).click();
    await status('Close all blocking issues before closing this issue');
    assert.equal(await issue.getByText('open', {exact: true}).count(), 1);
    const parser = page.locator('[data-testid="issues"] article').filter({has: page.getByRole('heading', {name: 'Implement parser fix', exact: true})});
    await parser.getByRole('button', {name: 'Close issue', exact: true}).click(); await status('Issue closed');
    await issue.getByRole('button', {name: 'Close issue', exact: true}).click();
    await issue.getByText('closed', {exact: true}).waitFor();
    assert.match(await issue.textContent(), /Morgan/);
    assert.match(await issue.textContent(), /Reviewed in browser/);
  } else if (app === 'approval_desk') {
    await page.getByLabel('Expense title', {exact: true}).fill('Browser equipment order');
    await page.getByRole('button', {name: 'Create expense', exact: true}).click(); await status('Expense created');
    const expense = page.locator('[data-testid="expenses"] article').filter({has: page.getByRole('heading', {name: 'Browser equipment order', exact: true})});
    await expense.getByLabel('Line description', {exact: true}).fill('Workstation');
    await expense.getByLabel('Quantity', {exact: true}).fill('2');
    await expense.getByLabel('Unit price (cents)', {exact: true}).fill('30000');
    await expense.getByRole('button', {name: 'Add line item', exact: true}).click(); await status('Line item added');
    await expense.getByRole('button', {name: 'Submit expense', exact: true}).click(); await status('Expense submitted');
    assert.match(await expense.textContent(), /60000 cents/);
    await expense.getByRole('button', {name: 'Approve step 2', exact: true}).click(); await status('Approval must follow step order');
    await expense.getByRole('button', {name: 'Approve step 1', exact: true}).click(); await status('Approval recorded');
    await expense.getByRole('button', {name: 'Approve step 2', exact: true}).click();
    await expense.getByText('approved', {exact: true}).waitFor();
    await expense.getByRole('button', {name: 'Pay expense', exact: true}).click(); await status('Expense paid');
    await expense.getByText('paid', {exact: true}).waitFor();
    assert.match(await expense.textContent(), /PAY-/);
  } else if (app === 'stock_room') {
    await page.getByLabel('Receipt SKU', {exact: true}).selectOption({label: 'Sensor (SEN-01)'});
    await page.getByLabel('Receipt quantity', {exact: true}).fill('4');
    await page.getByRole('button', {name: 'Receive stock', exact: true}).click(); await status('Stock received');
    await page.getByLabel('Reservation SKU', {exact: true}).selectOption({label: 'Sensor (SEN-01)'});
    await page.getByLabel('Order reference', {exact: true}).fill('BROWSER-TOO-MUCH');
    await page.getByLabel('Reservation quantity', {exact: true}).fill('999');
    await page.getByRole('button', {name: 'Reserve stock', exact: true}).click(); await status('Insufficient available stock');
    await page.getByLabel('Order reference', {exact: true}).fill('BROWSER-ORDER');
    await page.getByLabel('Reservation quantity', {exact: true}).fill('3');
    await page.getByRole('button', {name: 'Reserve stock', exact: true}).click(); await status('Stock reserved');
    const reservation = page.locator('[data-testid="reservations"] article').filter({has: page.getByRole('heading', {name: 'BROWSER-ORDER', exact: true})});
    await reservation.getByRole('button', {name: 'Dispatch reservation', exact: true}).click(); await status('Reservation dispatched');
    await reservation.getByText('dispatched', {exact: true}).waitFor();
    assert.equal(await reservation.getByRole('button').count(), 0);
    const sensor = page.locator('[data-testid="stock-totals"] article').filter({has: page.getByRole('heading', {name: 'Sensor', exact: true})});
    assert.match(await sensor.textContent(), /dispatched 11/);
  } else if (app === 'clinic_queue') {
    const slot = page.locator('[data-testid="slots"] article').filter({has: page.getByRole('heading', {name: 'Dr. Taylor 11:00', exact: true})});
    await slot.getByLabel('Patient name', {exact: true}).fill('Browser Patient');
    await slot.getByRole('button', {name: 'Book appointment', exact: true}).click(); await status('Appointment booked');
    assert.match(await slot.textContent(), /Browser Patient — booked/);
    await slot.getByRole('button', {name: 'Cancel appointment', exact: true}).click(); await status('Appointment cancelled');
    await slot.getByLabel('Patient name', {exact: true}).fill('Browser Rebook');
    await slot.getByRole('button', {name: 'Book appointment', exact: true}).click(); await status('Appointment booked');
    assert.match(await slot.textContent(), /Browser Rebook — booked/);
    assert.match(await slot.textContent(), /Browser Patient — cancelled/);
  } else if (app === 'course_path') {
    await page.getByLabel('Learner name', {exact: true}).fill('Browser Learner');
    await page.getByRole('button', {name: 'Enroll learner', exact: true}).click(); await status('Learner enrolled');
    const learner = page.getByTestId('enrollment').filter({has: page.getByRole('heading', {name: 'Browser Learner', exact: true})});
    await learner.getByRole('button', {name: 'Complete Edges', exact: true}).click(); await status('Complete every prerequisite before this lesson');
    for (const lesson of ['Nodes', 'Edges', 'Traversal', 'Optimization', 'Checkpoint reasoning']) {
      const control = learner.getByRole('button', {name: 'Complete ' + lesson, exact: true});
      await control.click(); await control.waitFor({state: 'detached'});
    }
    assert.match(await learner.textContent(), /5 of 5 lessons completed/);
  } else if (app === 'library_loans') {
    const title = page.getByTestId('titles').locator('article').filter({has: page.getByRole('heading', {name: 'Graph Thinking', exact: true})});
    await title.getByLabel('Patron', {exact: true}).selectOption({label: 'Avery'});
    await title.getByRole('button', {name: 'Borrow title', exact: true}).click(); await status('Title borrowed');
    await title.getByLabel('Patron', {exact: true}).selectOption({label: 'Morgan'});
    await title.getByRole('button', {name: 'Borrow title', exact: true}).click();
    await page.getByTestId('loans').locator('article').filter({has: page.getByRole('heading', {name: 'Graph Thinking — Morgan', exact: true})}).getByRole('button', {name: 'Return loan', exact: true}).waitFor();
    await title.getByLabel('Patron', {exact: true}).selectOption({label: 'Jordan'});
    await title.getByRole('button', {name: 'Place hold', exact: true}).click(); await status('Hold queued');
    const avery = page.getByTestId('loans').locator('article').filter({has: page.getByRole('heading', {name: 'Graph Thinking — Avery', exact: true})}).filter({has: page.getByRole('button', {name: 'Return loan', exact: true})});
    await avery.getByRole('button', {name: 'Return loan', exact: true}).click(); await status('Loan returned; hold queue processed');
    const jordan = page.getByTestId('loans').locator('article').filter({has: page.getByRole('heading', {name: 'Graph Thinking — Jordan', exact: true})}).filter({has: page.getByRole('button', {name: 'Return loan', exact: true})});
    assert.equal(await jordan.count(), 1);
    assert.match(await title.textContent(), /Jordan — fulfilled/);
    assert.match(await title.textContent(), /0 of 2 copies available/);
  } else if (app === 'event_seats') {
    const event = page.getByTestId('event').filter({has: page.getByRole('heading', {name: 'Graph Summit', exact: true})});
    await event.getByLabel('Seat A1', {exact: true}).check();
    await event.getByLabel('Seat A2', {exact: true}).check();
    await event.getByLabel('Booking reference', {exact: true}).fill('BROWSER-BOOKING');
    await event.getByRole('button', {name: 'Hold selected seats', exact: true}).click(); await status('Seats held');
    const booking = event.getByTestId('booking').filter({has: page.getByRole('heading', {name: 'BROWSER-BOOKING', exact: true})});
    await booking.getByRole('button', {name: 'Confirm booking', exact: true}).click(); await status('Booking confirmed');
    assert.equal(await event.getByLabel('Seat A1', {exact: true}).isDisabled(), true);
    await booking.getByRole('button', {name: 'Cancel booking', exact: true}).click(); await status('Booking cancelled');
    await booking.getByText('cancelled', {exact: true}).waitFor();
    assert.equal(await event.getByLabel('Seat A1', {exact: true}).isEnabled(), true);
    assert.equal(await event.getByLabel('Seat A2', {exact: true}).isEnabled(), true);
    assert.match(await booking.textContent(), /Refund:/);
  } else if (app === 'help_queue') {
    await page.getByLabel('Ticket subject', {exact: true}).fill('Browser escalation');
    await page.getByLabel('Priority', {exact: true}).selectOption('urgent');
    await page.getByRole('button', {name: 'Open ticket', exact: true}).click(); await status('Ticket opened');
    const ticket = page.getByTestId('tickets').locator('article').filter({has: page.getByRole('heading', {name: 'Browser escalation', exact: true})});
    await ticket.getByRole('button', {name: 'Resolve ticket', exact: true}).click(); await status('Only open tickets with a reply can be resolved');
    await page.getByLabel('Advance minutes', {exact: true}).fill('30');
    await page.getByRole('button', {name: 'Advance clock', exact: true}).click(); await status('Clock advanced');
    await page.getByRole('button', {name: 'Evaluate SLA', exact: true}).click(); await status('SLA evaluated');
    assert.match(await ticket.textContent(), /Assigned: Sam; Escalated/);
    await ticket.getByLabel('Reply message', {exact: true}).fill('Replaced the test sensor');
    await ticket.getByRole('button', {name: 'Send reply', exact: true}).click(); await status('Reply sent');
    await ticket.getByRole('button', {name: 'Resolve ticket', exact: true}).click(); await status('Ticket resolved');
    await ticket.getByText('resolved', {exact: true}).waitFor();
  } else await runAdditional(app, page, status);
  await page.screenshot({path: directory + '/browser.png', fullPage: true});
  const events = await page.evaluate(() => window.suiteEvents);
  assert.equal(errors.length, 0, errors.join('\n'));
  await fs.writeFile(directory + '/browser-result.json', JSON.stringify({app, status: 'passed',
    browser: await browser.version(), workflow: 'Real DOM inputs, clicks and native HTTP requests', events, page_errors: errors}, null, 2));
  console.log(app + ': browser workflow passed');
} finally {
  await context.tracing.stop({path: directory + '/browser-trace.zip'});
  await browser.close();
}
