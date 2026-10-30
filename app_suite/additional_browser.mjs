import assert from 'node:assert/strict';
export async function runAdditional(app, page, status) {
  const card = name => page.locator('article').filter({has: page.getByRole('heading', {name, exact: true})});
  if (app === 'recipe_pantry') {
    await page.getByLabel('Meal name', {exact:true}).fill('Browser breakfast');
    await page.getByLabel('Servings', {exact:true}).fill('1');
    await page.getByLabel('Recipe', {exact:true}).selectOption({label:'Breakfast porridge'});
    await page.getByRole('button', {name:'Plan meal',exact:true}).click(); await status('Meal planned');
    await card('Browser breakfast').getByRole('button', {name:'Cook meal',exact:true}).click(); await status('Buy missing ingredients before cooking');
    for (const [name, units] of [['Rolled oats','2'],['Milk','1']]) {
      await card(name).getByLabel('Purchase units', {exact:true}).fill(units);
      await card(name).getByRole('button', {name:'Buy ingredient',exact:true}).click(); await status('Ingredient purchased');
    }
    await card('Browser breakfast').getByRole('button', {name:'Cook meal',exact:true}).click(); await status('Meal cooked');
    assert.match(await card('Browser breakfast').textContent(), /cooked/);
  } else if (app === 'trip_board') {
    await page.getByLabel('Stop name', {exact:true}).fill('Browser garden');
    await page.getByLabel('Day number', {exact:true}).fill('2');
    await page.getByRole('button', {name:'Add stop',exact:true}).click(); await status('Stop added');
    await card('Browser garden').getByLabel('Guests',{exact:true}).fill('9');
    await card('Browser garden').getByRole('button',{name:'Reserve stay',exact:true}).click(); await status('Stay capacity would be exceeded');
    await card('Browser garden').getByLabel('Guests',{exact:true}).fill('2');
    await card('Browser garden').getByRole('button',{name:'Reserve stay',exact:true}).click(); await status('Stay reserved');
    await card('Browser garden').getByRole('button',{name:'Move earlier',exact:true}).click(); await status('Itinerary reordered');
    assert.match(await card('Browser garden').textContent(), /guests 2\/4/);
  } else if(app==='delivery_route'){
    await page.getByLabel('Route name',{exact:true}).fill('Browser route'); await page.getByLabel('Weight capacity',{exact:true}).fill('10');
    await page.getByRole('button',{name:'Create route',exact:true}).click(); await status('Route created');
    const r=card('Browser route'); await r.getByLabel('Parcel',{exact:true}).selectOption({label:'Spare crate (8)'});
    await r.getByRole('button',{name:'Assign parcel',exact:true}).click(); await status('Parcel assigned');
    await r.getByRole('button',{name:'Load route',exact:true}).click(); await status('Route loaded');
    await r.getByLabel('Failure reason',{exact:true}).fill('No recipient'); await r.getByRole('button',{name:'Record failed attempt',exact:true}).click(); await status('Delivery failed');
    await r.getByRole('button',{name:'Retry failed stop',exact:true}).click(); await status('Stop ready for retry');
    await r.getByRole('button',{name:'Deliver next',exact:true}).click(); await status('Parcel delivered'); assert.match(await r.textContent(),/Complete/);
  } else if(app==='hiring_pipeline'){
    await page.getByLabel('Candidate name',{exact:true}).fill('Browser Candidate'); await page.getByRole('button',{name:'Add candidate',exact:true}).click(); await status('Candidate added');
    const j=card('Developer Advocate'); await j.getByLabel('Candidate',{exact:true}).selectOption({label:'Browser Candidate'}); await j.getByRole('button',{name:'Apply to job',exact:true}).click(); await status('Application created');
    const a=card('Developer Advocate: Browser Candidate');
    for(const round of ['technical','collaboration']){
      await a.getByRole('button',{name:'Schedule '+round,exact:true}).click(); await status('Interview scheduled');
      await a.getByLabel(round+' score',{exact:true}).fill('5'); await a.getByRole('button',{name:'Score '+round,exact:true}).click(); await status('Score saved');
    }
    await a.getByRole('button',{name:'Make offer',exact:true}).click(); await status('Offer made'); assert.match(await a.textContent(),/offered/);
  } else if(app==='sales_pipeline'){
    const a=card('South Lab');await a.getByLabel('Opportunity title',{exact:true}).fill('Browser expansion');await a.getByRole('button',{name:'Create opportunity',exact:true}).click();await status('Opportunity created');
    const o=card('Browser expansion');await o.getByLabel('Activity note',{exact:true}).fill('Confirmed procurement');await o.getByRole('button',{name:'Log activity',exact:true}).click();await status('Activity recorded');
    await o.getByRole('button',{name:'Qualify opportunity',exact:true}).click();await status('Opportunity qualified');
    await o.getByLabel('Quote quantity',{exact:true}).fill('2');await o.getByLabel('Unit price cents',{exact:true}).fill('25000');await o.getByRole('button',{name:'Create quote',exact:true}).click();await status('Quote created');
    await o.getByRole('button',{name:'Accept quote',exact:true}).click();await status('Quote accepted');await o.getByRole('button',{name:'Close won',exact:true}).click();await status('Opportunity won');assert.match(await o.textContent(),/50000 cents/);
  } else if(app==='grant_review'){
    const p=card('Compiler verification');
    for(const name of ['Alex','Blair']){
      await p.getByLabel('Reviewer',{exact:true}).selectOption({label:name});await p.getByRole('button',{name:'Assign reviewer',exact:true}).click();await status('Reviewer assigned');
      await p.getByLabel(name+' merit',{exact:true}).fill('5');await p.getByLabel(name+' feasibility',{exact:true}).fill('5');await p.getByRole('button',{name:'Submit '+name+' review',exact:true}).click();await status('Review submitted');
    }
    await p.getByRole('button',{name:'Release proposal',exact:true}).click();await status('Proposal released');assert.match(await p.textContent(),/weighted score 30/);
  } else if(app==='lab_samples'){
    await page.getByLabel('Batch name',{exact:true}).fill('Browser batch');await page.getByRole('button',{name:'Create batch',exact:true}).click();await status('Batch created');
    await card('Water sample').getByLabel('Aliquot volume',{exact:true}).fill('10');await card('Water sample').getByRole('button',{name:'Split sample',exact:true}).click();await status('Sample split');
    const batch=card('Browser batch');await batch.getByLabel('Aliquot',{exact:true}).selectOption({label:'Water sample aliquot 3'});await batch.getByRole('button',{name:'Add aliquot',exact:true}).click();await status('Aliquot assigned');
    await batch.getByRole('button',{name:'Release batch',exact:true}).click();await status('Every aliquot must pass its latest quality-control test');
    const a=card('Water sample aliquot 3');await a.getByLabel('Assay value',{exact:true}).fill('15');await a.getByRole('button',{name:'Record result',exact:true}).click();await status('Result recorded');
    await batch.getByRole('button',{name:'Release batch',exact:true}).click();await status('Batch released');assert.match(await batch.textContent(),/Released/);
  } else if(app==='asset_care'){
    const a=card('Valve V1');await a.getByLabel('Inspection issue',{exact:true}).fill('Leaking valve');await a.getByLabel('Severity',{exact:true}).fill('4');await a.getByRole('button',{name:'Inspect asset',exact:true}).click();await status('Inspection recorded');
    await a.getByRole('button',{name:'Open work order',exact:true}).click();await status('Work order opened');const o=card('Valve V1 order 1');
    await o.getByLabel('Parts quantity',{exact:true}).fill('1');await o.getByRole('button',{name:'Use part',exact:true}).click();await status('Part consumed');
    await o.getByRole('button',{name:'Finish work order',exact:true}).click();await status('Work order completed');assert.match(await a.textContent(),/operational/);
  } else if(app==='utility_meter'){
    const m=card('Power');await m.getByLabel('New reading',{exact:true}).fill('1200');await m.getByRole('button',{name:'Record reading',exact:true}).click();await status('Reading recorded');await m.getByRole('button',{name:'Bill latest interval',exact:true}).click();await status('Invoice created');assert.match(await m.textContent(),/total billed 580 cents/);
  } else if(app==='volunteer_shift'){
    const s=card('Safety desk');await s.getByLabel('Volunteer',{exact:true}).selectOption({label:'Avery (First aid)'});await s.getByRole('button',{name:'Join shift',exact:true}).click();await status('Signup recorded');assert.match(await s.textContent(),/Avery: waitlisted/);
    await s.getByRole('button',{name:'Cancel Casey',exact:true}).click();await status('Signup cancelled');assert.match(await s.textContent(),/Avery: confirmed/);
  } else if(app==='poll_assembly'){
    const m=card('Release vote');for(const voter of ['Avery','Morgan']){await m.getByLabel('Voter',{exact:true}).selectOption({label:voter});await m.getByLabel('Option',{exact:true}).selectOption({label:'Yes'});await m.getByRole('button',{name:'Cast ballot',exact:true}).click();await status('Ballot saved');}
    await m.getByRole('button',{name:'Close motion',exact:true}).click();await status('Motion closed');assert.match(await m.textContent(),/passed; 2 ballots/);
  } else if(app==='budget_ledger'){
    const e=card('Equipment');await e.getByLabel('Allocation cents',{exact:true}).fill('10000');await e.getByRole('button',{name:'Allocate funds',exact:true}).click();await status('Funds allocated');
    await e.getByLabel('Expense cents',{exact:true}).fill('1000');await e.getByRole('button',{name:'Record expense',exact:true}).click();await status('Expense recorded');
    await page.getByLabel('Source envelope',{exact:true}).selectOption({label:'Equipment'});await page.getByLabel('Destination envelope',{exact:true}).selectOption({label:'Travel'});
    await page.getByLabel('Transfer cents',{exact:true}).fill('2000');await page.getByLabel('Transfer reference',{exact:true}).fill('BROWSER-TRANSFER');await page.getByRole('button',{name:'Transfer funds',exact:true}).click();await status('Transfer recorded');assert.match(await e.textContent(),/27000 cents/);
  } else if(app==='build_release'){
    await page.getByLabel('Build label',{exact:true}).fill('Browser build');await page.getByRole('button',{name:'Create build',exact:true}).click();await status('Build created');const b=card('Browser build');
    for(const name of ['unit','integration','security']){await b.getByRole('button',{name:'Pass '+name,exact:true}).click();await status('Check recorded');await b.getByText(new RegExp(name+': passed')).waitFor();}
    await b.getByRole('button',{name:'Deploy to staging',exact:true}).click();await status('Build deployed');assert.match(await b.textContent(),/deployed/);
  } else if(app==='knowledge_map'){
    const a=card('Release handbook');await a.getByLabel('Revision text',{exact:true}).fill('Browser research note');await a.getByRole('button',{name:'Save revision',exact:true}).click();await status('Revision saved');
    await a.getByLabel('Review note',{exact:true}).fill('Approved for advisor');await a.getByRole('button',{name:'Review latest revision',exact:true}).click();await status('Revision reviewed');await a.getByRole('button',{name:'Publish latest revision',exact:true}).click();await status('Article published');
    await a.getByLabel('Target article',{exact:true}).selectOption({label:'Storage notes'});await a.getByRole('button',{name:'Link article',exact:true}).click();await status('Articles linked');await a.getByRole('button',{name:'Explore links',exact:true}).click();await status('Links explored');assert.match(await a.textContent(),/Published revision 2/);
  } else if(app==='return_counter'){
    const l=card('Cable pack');await l.getByLabel('Return quantity',{exact:true}).fill('2');await l.getByLabel('Return reference',{exact:true}).fill('BROWSER-RETURN');await l.getByRole('button',{name:'Request return',exact:true}).click();await status('Return requested');const r=card('BROWSER-RETURN');await r.getByRole('button',{name:'Accept inspection',exact:true}).click();await status('Inspection recorded');await r.getByRole('button',{name:'Issue refund',exact:true}).click();await status('Refund issued');assert.match(await r.textContent(),/refunded 400 cents/);
  } else if(app==='garden_plan'){
    const plot=card('South bed');await plot.getByLabel('Planting area',{exact:true}).fill('4');await plot.getByLabel('Crop',{exact:true}).selectOption({label:'Tomato'});await plot.getByRole('button',{name:'Plant crop',exact:true}).click();await status('Crop planted');const p=card('South bed Tomato planting 1');
    for(const name of ['Water','Inspect']){await p.getByRole('button',{name:'Complete '+name,exact:true}).click();await status('Garden task completed');await p.getByText(name+': done',{exact:true}).waitFor();}
    await p.getByLabel('Harvest quantity',{exact:true}).fill('3');await p.getByRole('button',{name:'Record harvest',exact:true}).click();await status('Harvest recorded');assert.match(await p.textContent(),/harvested; harvest 3/);
  } else if(app==='tournament'){
    await page.getByLabel('Tournament name',{exact:true}).fill('Browser cup');await page.getByRole('button',{name:'Create tournament',exact:true}).click();await status('Tournament created');
    for(const [round,position,home,away]of [[1,1,'3','1'],[1,2,'2','0'],[2,1,'1','2']]){const m=card(`Browser cup round ${round} match ${position}`);await m.getByLabel('Home score',{exact:true}).fill(home);await m.getByLabel('Away score',{exact:true}).fill(away);await m.getByRole('button',{name:'Record score',exact:true}).click();await status('Score recorded');await m.getByRole('button',{name:'Record score',exact:true}).waitFor({state:'detached'});}
    assert.match(await card('Browser cup round 2 match 1').textContent(),/winner Cedar/);
  } else if(app==='incident_room'){
    const s=card('API');await s.getByLabel('Incident summary',{exact:true}).fill('Browser outage');await s.getByRole('button',{name:'Open incident',exact:true}).click();await status('Incident opened');const i=card('Browser outage');
    await i.getByRole('button',{name:'Resolve incident',exact:true}).click();await status('Acknowledge every alert and complete every action before resolution');
    for(const name of ['API','Database','Cache']){await i.getByRole('button',{name:'Acknowledge '+name,exact:true}).click();await status('Alert acknowledged');await i.getByText(name+': acknowledged',{exact:true}).waitFor();}
    await i.getByRole('button',{name:'Complete Investigate cause',exact:true}).click();await status('Incident action completed');await i.getByRole('button',{name:'Resolve incident',exact:true}).click();await status('Incident resolved');assert.match(await i.textContent(),/resolved/);
  } else throw new Error('No browser workflow for ' + app);
}
