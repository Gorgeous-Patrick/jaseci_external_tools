// Shared UI primitives support independently authored domain workflows.
export const domainTitles = {recipe_pantry: 'RecipePantry', trip_board: 'TripBoard', delivery_route: 'DeliveryRoute', hiring_pipeline: 'HiringPipeline', sales_pipeline:'SalesPipeline', grant_review:'GrantReview', lab_samples:'LabSamples', asset_care:'AssetCare'};
Object.assign(domainTitles,{utility_meter:'UtilityMeter',volunteer_shift:'VolunteerShift',poll_assembly:'PollAssembly'});
Object.assign(domainTitles,{budget_ledger:'BudgetLedger',build_release:'BuildRelease',knowledge_map:'KnowledgeMap'});
Object.assign(domainTitles,{return_counter:'ReturnCounter',garden_plan:'GardenPlan',tournament:'Tournament',incident_room:'IncidentRoom'});
const renderers = {};
export async function renderDomain(app, ui) {
  const render = renderers[app];
  if (!render) throw new Error('Application frontend is not implemented');
  const refresh = () => renderDomain(app, ui);
  const action = async (name, body, text) => {
    const result = (await ui.walker(name, body))[0];
    if (!result.ok) throw new Error(result.error);
    ui.uiEvents.push({action: name, ...body, result}); await refresh(); ui.message(text);
  };
  const select = (form, name, label, rows) => {
    const wrapper = ui.element('label', label), input = ui.element('select', null, {name, 'aria-label': label});
    for (const [value, text] of rows) input.append(ui.element('option', text, {value}));
    wrapper.append(input); form.prepend(wrapper); return input;
  };
  const card = (title, text, id) => {
    const item = ui.element('article', null, {'data-id': id || title});
    item.append(ui.element('h3', title), ui.element('p', text)); return item;
  };
  ui.workspace.replaceChildren();
  await render({...ui, action, select, card});
}

renderers.recipe_pantry = async u => {
  const b = (await u.walker('PantryBoard'))[0];
  u.workspace.append(u.element('h2', 'Meal plans and pantry'));
  const plan = u.form([['name', 'Meal name'], ['servings', 'Servings', 'number']], 'Plan meal', v => u.action('PlanMeal', {...v, servings: Number(v.servings)}, 'Meal planned'));
  u.select(plan, 'recipe_id', 'Recipe', b.recipes.map(r => [r.id, r.name])); u.workspace.append(plan);
  for (const i of b.ingredients) {
    const c = u.card(i.name, `${i.units} units available`, i.id);
    c.append(u.form([['quantity', 'Purchase units', 'number']], 'Buy ingredient', v => u.action('BuyIngredient', {ingredient_id: i.id, quantity: Number(v.quantity)}, 'Ingredient purchased'))); u.workspace.append(c);
  }
  u.workspace.append(u.button('Calculate shopping list', async () => {
    const rows = (await u.walker('ShoppingList'))[0];
    const panel = u.element('section', null, {'data-testid': 'shopping'});
    for (const r of rows) panel.append(u.element('p', `${r.name}: need ${r.required}, buy ${r.shortage}`));
    u.workspace.append(panel); u.message('Shopping list calculated');
  }));
  for (const m of b.meals) {
    const c = u.card(m.name, `${m.servings} servings; ${m.status}`, m.id);
    if (m.status === 'planned') c.append(u.button('Cook meal', () => u.action('CookMeal', {meal_id: m.id}, 'Meal cooked'))); u.workspace.append(c);
  }
};

renderers.trip_board = async u => {
  const b = (await u.walker('Itinerary'))[0];
  for (const j of b.journeys) {
    u.workspace.append(u.element('h2', j.name));
    const add = u.form([['name', 'Stop name'], ['day', 'Day number', 'number']], 'Add stop', v => u.action('AddStop', {journey_id: j.id, name: v.name, day: Number(v.day)}, 'Stop added'));
    u.workspace.append(add);
    for (const s of j.stops) {
      const c = u.card(s.name, `Day ${s.day}; position ${s.position}; guests ${s.booked}/${s.capacity}`, s.id);
      c.append(u.form([['guests', 'Guests', 'number']], 'Reserve stay', v => u.action('ReserveStay', {stop_id: s.id, guests: Number(v.guests)}, 'Stay reserved')),
        u.button('Move earlier', () => u.action('MoveStop', {stop_id: s.id, position: Math.max(1, s.position - 1)}, 'Itinerary reordered')));
      for (const r of s.bookings.filter(r => r.active)) c.append(u.button('Cancel stay', () => u.action('CancelStay', {booking_id: r.id}, 'Stay cancelled')));
      u.workspace.append(c);
    }
  }
};

renderers.delivery_route = async u => {
  const b = (await u.walker('RouteBoard'))[0]; u.workspace.append(u.element('h2','Parcel dispatch'));
  u.workspace.append(u.form([['name','Route name'],['capacity','Weight capacity','number']], 'Create route', v => u.action('CreateRoute',{name:v.name,capacity:Number(v.capacity)},'Route created')));
  for (const r of b.routes) {
    const c = u.card(r.name, `${r.loaded ? 'Loaded' : 'Not loaded'}; ${r.complete ? 'Complete' : 'In progress'}`,r.id);
    if (!r.loaded) {
      const f = u.form([], 'Assign parcel',v => u.action('AssignParcel',{route_id:r.id,parcel_id:v.parcel_id},'Parcel assigned'));
      u.select(f,'parcel_id','Parcel',b.parcels.filter(p=>p.status==='waiting').map(p=>[p.id,`${p.label} (${p.weight})`]));
      c.append(f,u.button('Load route',()=>u.action('LoadRoute',{route_id:r.id},'Route loaded')));
    } else if (!r.complete) c.append(u.button('Deliver next',()=>u.action('DeliveryAttempt',{route_id:r.id,success:true},'Parcel delivered')),
      u.form([['note','Failure reason']], 'Record failed attempt',v=>u.action('DeliveryAttempt',{route_id:r.id,success:false,note:v.note},'Delivery failed')));
    for (const s of r.stops) {
      c.append(u.element('p',`${s.position}. ${s.label}: ${s.status}`));
      if(s.status==='failed') c.append(u.button('Retry failed stop',()=>u.action('RetryStop',{stop_id:s.id},'Stop ready for retry')));
    }
    u.workspace.append(c);
  }
};

renderers.hiring_pipeline = async u => {
  const b=(await u.walker('HiringBoard'))[0]; u.workspace.append(u.element('h2','Hiring and interviews'));
  u.workspace.append(u.form([['name','Candidate name']],'Add candidate',v=>u.action('CreateCandidate',v,'Candidate added')));
  for(const j of b.jobs){
    const c=u.card(j.title,`${j.positions} position; required score ${j.threshold}`,j.id);
    const f=u.form([],'Apply to job',v=>u.action('ApplyJob',{job_id:j.id,candidate_id:v.candidate_id},'Application created'));
    u.select(f,'candidate_id','Candidate',b.candidates.map(p=>[p.id,p.name])); c.append(f); u.workspace.append(c);
    for(const a of j.applications){
      const item=u.card(`${j.title}: ${a.candidate}`,a.status,a.id);
      if(a.status==='applied'){
        for(const round of ['technical','collaboration']){
          const interview=a.interviews.find(i=>i.round===round);
          if(!interview) item.append(u.button('Schedule '+round,()=>u.action('ScheduleInterview',{application_id:a.id,round},'Interview scheduled')));
          else if(!interview.scores.length) item.append(u.form([['score',round+' score','number']],'Score '+round,v=>u.action('ScoreInterview',{interview_id:interview.id,score:Number(v.score)},'Score saved')));
          else item.append(u.element('p',`${round}: ${interview.scores[0]}/5`));
        }
        item.append(u.button('Make offer',()=>u.action('OfferApplication',{application_id:a.id},'Offer made')));
      }
      u.workspace.append(item);
    }
  }
};

renderers.sales_pipeline=async u=>{
  const b=(await u.walker('SalesBoard'))[0]; u.workspace.append(u.element('h2',`Sales revenue: ${b.won_cents} cents`));
  for(const a of b.accounts){
    const c=u.card(a.name,`Contacts: ${a.contacts.join(', ')}`,a.id);
    c.append(u.form([['title','Opportunity title']],'Create opportunity',v=>u.action('CreateOpportunity',{account_id:a.id,...v},'Opportunity created'))); u.workspace.append(c);
    for(const o of a.opportunities){
      const item=u.card(o.title,`${o.stage}; ${o.amount_cents} cents`,o.id);
      for(const note of o.activities)item.append(u.element('p',note));
      if(!['won','lost'].includes(o.stage))item.append(u.form([['note','Activity note']],'Log activity',v=>u.action('LogActivity',{opportunity_id:o.id,...v},'Activity recorded')));
      if(o.stage==='open')item.append(u.button('Qualify opportunity',()=>u.action('QualifyOpportunity',{opportunity_id:o.id},'Opportunity qualified')));
      if(o.stage==='qualified'){
        item.append(u.form([['quantity','Quote quantity','number'],['unit_cents','Unit price cents','number']],'Create quote',v=>u.action('CreateQuote',{opportunity_id:o.id,quantity:Number(v.quantity),unit_cents:Number(v.unit_cents)},'Quote created')));
        for(const q of o.quotes){item.append(u.element('p',`Quote ${q.total_cents} cents; ${q.accepted?'accepted':'pending'}`));if(!q.accepted)item.append(u.button('Accept quote',()=>u.action('AcceptQuote',{quote_id:q.id},'Quote accepted')));}
        item.append(u.button('Close won',()=>u.action('CloseWon',{opportunity_id:o.id},'Opportunity won')));
      } u.workspace.append(item);
    }
  }
};

renderers.grant_review=async u=>{
  const b=(await u.walker('ReviewBoard'))[0]; u.workspace.append(u.element('h2','Proposal review panel'));
  for(const p of b.proposals){
    const c=u.card(p.title,`${p.released?'Released':'Under review'}; weighted score ${p.score_total} from ${p.review_count} reviews`,p.id);
    if(!p.released){const f=u.form([],'Assign reviewer',v=>u.action('AssignReviewer',{proposal_id:p.id,...v},'Reviewer assigned'));u.select(f,'reviewer_id','Reviewer',b.reviewers.map(r=>[r.id,r.name]));c.append(f);}
    for(const a of p.assignments){c.append(u.element('p',`${a.reviewer}: ${a.submitted?'submitted':'pending'}`));if(!a.submitted)c.append(u.form([['merit',a.reviewer+' merit','number'],['feasibility',a.reviewer+' feasibility','number']],'Submit '+a.reviewer+' review',v=>u.action('SubmitReview',{assignment_id:a.id,merit:Number(v.merit),feasibility:Number(v.feasibility)},'Review submitted')));}
    if(!p.released)c.append(u.button('Release proposal',()=>u.action('ReleaseProposal',{proposal_id:p.id},'Proposal released')));u.workspace.append(c);
  }
};

renderers.lab_samples=async u=>{
  const b=(await u.walker('LabBoard'))[0];u.workspace.append(u.element('h2','Sample lineage and quality control'));
  u.workspace.append(u.form([['name','Batch name']],'Create batch',v=>u.action('CreateBatch',v,'Batch created')));
  for(const s of b.samples){const c=u.card(s.name,`${s.remaining}/${s.initial} volume remaining`,s.id);c.append(u.form([['volume','Aliquot volume','number']],'Split sample',v=>u.action('SplitSample',{sample_id:s.id,volume:Number(v.volume)},'Sample split')));u.workspace.append(c);
    for(const a of s.aliquots){const item=u.card(`${s.name} aliquot ${a.number}`,`${a.volume} volume; latest result ${a.results.length?a.results.at(-1).value:'not tested'}`,a.id);
      const f=u.form([['value','Assay value','number']],'Record result',v=>u.action('RecordResult',{aliquot_id:a.id,assay_id:v.assay_id,value:Number(v.value)},'Result recorded'));
      u.select(f,'assay_id','Assay',b.assays.map(x=>[x.id,x.name]));item.append(f);u.workspace.append(item);}}
  for(const batch of b.batches){const c=u.card(batch.name,`${batch.released?'Released':'Unreleased'}; ${batch.aliquots.length} aliquots`,batch.id);
    if(!batch.released){const f=u.form([],'Add aliquot',v=>u.action('AddAliquot',{batch_id:batch.id,...v},'Aliquot assigned'));u.select(f,'aliquot_id','Aliquot',b.samples.flatMap(s=>s.aliquots.filter(a=>!a.assigned).map(a=>[a.id,`${s.name} aliquot ${a.number}`])));c.append(f,u.button('Release batch',()=>u.action('ReleaseBatch',{batch_id:batch.id},'Batch released')));}u.workspace.append(c);}
};

renderers.asset_care=async u=>{
  const b=(await u.walker('AssetBoard'))[0];u.workspace.append(u.element('h2','Asset inspections and maintenance'));
  for(const p of b.parts)u.workspace.append(u.element('p',`${p.name}: ${p.stock}/${p.initial} parts remaining`));
  for(const a of b.assets){const c=u.card(a.name,a.status,a.id);
    c.append(u.form([['issue','Inspection issue'],['severity','Severity','number']],'Inspect asset',v=>u.action('InspectAsset',{asset_id:a.id,issue:v.issue,severity:Number(v.severity)},'Inspection recorded')));
    const f=u.form([],'Open work order',v=>u.action('OpenWorkOrder',{asset_id:a.id,...v},'Work order opened'));u.select(f,'technician_id','Technician',b.technicians.map(t=>[t.id,t.name]));c.append(f);u.workspace.append(c);
    for(const o of a.orders){const item=u.card(`${a.name} order ${o.number}`,`${o.status}; parts used ${o.uses.reduce((s,x)=>s+x.quantity,0)}`,o.id);
      if(o.status==='open'){const consume=u.form([['quantity','Parts quantity','number']],'Use part',v=>u.action('ConsumePart',{order_id:o.id,part_id:v.part_id,quantity:Number(v.quantity)},'Part consumed'));u.select(consume,'part_id','Part',b.parts.map(p=>[p.id,p.name]));item.append(consume,u.button('Finish work order',()=>u.action('FinishWorkOrder',{order_id:o.id},'Work order completed')));}u.workspace.append(item);}
  }
};

renderers.utility_meter=async u=>{
  const b=(await u.walker('MeterBoard'))[0];u.workspace.append(u.element('h2','Meter readings and tiered billing'));
  for(const m of b.meters){const c=u.card(m.name,`Latest reading ${m.readings.at(-1).value}; total billed ${m.invoices.reduce((s,i)=>s+i.cents,0)} cents`,m.id);
    c.append(u.form([['value','New reading','number']],'Record reading',v=>u.action('AddReading',{meter_id:m.id,value:Number(v.value)},'Reading recorded')),
      u.form([['value','Corrected value','number']],'Correct latest reading',v=>u.action('CorrectReading',{reading_id:m.readings.at(-1).id,value:Number(v.value)},'Reading corrected')),
      u.button('Bill latest interval',()=>u.action('BillMeter',{meter_id:m.id},'Invoice created')));
    for(const i of m.invoices)c.append(u.element('p',`Invoice: ${i.units} units, ${i.cents} cents`));u.workspace.append(c);}
};

renderers.volunteer_shift=async u=>{
  const b=(await u.walker('VolunteerBoard'))[0];u.workspace.append(u.element('h2','Skills and volunteer rosters'));
  for(const s of b.shifts){const c=u.card(s.name,`Capacity ${s.capacity}`,s.id);const f=u.form([],'Join shift',v=>u.action('JoinShift',{shift_id:s.id,...v},'Signup recorded'));u.select(f,'volunteer_id','Volunteer',b.volunteers.map(v=>[v.id,`${v.name} (${v.skills.join(', ')})`]));c.append(f);
    for(const a of s.signups){c.append(u.element('p',`${a.volunteer}: ${a.status} (queue ${a.position})`));if(a.status!=='cancelled')c.append(u.button('Cancel '+a.volunteer,()=>u.action('CancelSignup',{signup_id:a.id},'Signup cancelled')));}u.workspace.append(c);}
};

renderers.poll_assembly=async u=>{
  const b=(await u.walker('AssemblyBoard'))[0];u.workspace.append(u.element('h2','Assembly motions and quorum'));
  for(const m of b.motions){const c=u.card(m.title,`${m.status}; ${m.outcome}; ${m.ballot_count} ballots`,m.id);
    for(const o of m.options)c.append(u.element('p',`${o.label}: ${o.votes}`));
    if(m.status==='open'){const f=u.form([],'Cast ballot',v=>u.action('CastBallot',{motion_id:m.id,...v},'Ballot saved'));u.select(f,'voter_id','Voter',b.voters.map(v=>[v.id,v.name]));u.select(f,'option_id','Option',m.options.map(o=>[o.id,o.label]));c.append(f,u.button('Close motion',()=>u.action('CloseMotion',{motion_id:m.id},'Motion closed')));}u.workspace.append(c);}
};

renderers.budget_ledger=async u=>{
  const b=(await u.walker('BudgetBoard'))[0];u.workspace.append(u.element('h2',`Budget: ${b.budgets[0]?.unallocated} cents unallocated`));
  for(const e of b.envelopes){const c=u.card(e.name,`${e.balance} cents available`,e.id);c.append(u.form([['amount','Allocation cents','number']],'Allocate funds',v=>u.action('AllocateBudget',{envelope_id:e.id,amount:Number(v.amount)},'Funds allocated')));
    const f=u.form([['amount','Expense cents','number']],'Record expense',v=>u.action('SpendEnvelope',{envelope_id:e.id,category_id:v.category_id,amount:Number(v.amount)},'Expense recorded'));u.select(f,'category_id','Category',b.categories.map(c=>[c.id,c.name]));c.append(f);u.workspace.append(c);}
  const t=u.form([['amount','Transfer cents','number'],['reference','Transfer reference']],'Transfer funds',v=>u.action('TransferBudget',{...v,amount:Number(v.amount)},'Transfer recorded'));
  for(const [name,label]of[['source_id','Source envelope'],['target_id','Destination envelope']])u.select(t,name,label,b.envelopes.map(e=>[e.id,e.name]));u.workspace.append(t);
  for(const t of b.transfers)u.workspace.append(u.element('p',`${t.reference}: ${t.amount} cents transferred`));
};

renderers.build_release=async u=>{
  const b=(await u.walker('ReleaseBoard'))[0];u.workspace.append(u.element('h2','Build checks and deployment'));
  for(const r of b.releases){u.workspace.append(u.form([['label','Build label']],'Create build',v=>u.action('CreateBuild',{release_id:r.id,...v},'Build created')));
    for(const build of r.builds){const c=u.card(build.label,`${build.status}; artifacts ${build.artifacts.length}`,build.id);
      for(const check of build.checks){c.append(u.element('p',`${check.name}: ${check.status}; requires ${check.dependencies.join(', ')||'nothing'}`));if(build.status!=='deployed')for(const passed of [true,false])c.append(u.button((passed?'Pass ':'Fail ')+check.name,()=>u.action('RecordCheck',{check_id:check.id,passed},'Check recorded')));}
      if(build.status!=='deployed')c.append(u.button('Deploy to staging',()=>u.action('DeployBuild',{build_id:build.id,environment:'staging'},'Build deployed')));u.workspace.append(c);}
  }
};

renderers.knowledge_map=async u=>{
  const b=(await u.walker('KnowledgeBoard'))[0];u.workspace.append(u.element('h2','Reviewed knowledge revisions'));
  for(const a of b.articles){const latest=a.revisions.at(-1);const c=u.card(a.title,`Published revision ${a.published_revision}; latest ${latest.number}: ${latest.body}; backlinks ${a.backlinks.join(', ')}`,a.id);
    c.append(u.form([['body','Revision text']],'Save revision',v=>u.action('ReviseArticle',{article_id:a.id,...v},'Revision saved')),
      u.form([['note','Review note']],'Review latest revision',v=>u.action('ReviewRevision',{revision_id:latest.id,...v},'Revision reviewed')),
      u.button('Publish latest revision',()=>u.action('PublishArticle',{article_id:a.id},'Article published')));
    const f=u.form([],'Link article',v=>u.action('LinkArticles',{source_id:a.id,...v},'Articles linked'));u.select(f,'target_id','Target article',b.articles.filter(x=>x.id!==a.id).map(x=>[x.id,x.title]));c.append(f,u.button('Explore links',async()=>{const titles=(await u.walker('ExploreLinks',{article_id:a.id}))[0];c.append(u.element('p','Reachable articles: '+titles.join(', ')));u.message('Links explored');}));u.workspace.append(c);
  }
};

renderers.return_counter=async u=>{
  const b=(await u.walker('ReturnBoard'))[0];u.workspace.append(u.element('h2','Merchandise returns and inspections'));
  for(const order of b.orders)for(const l of order.lines){const c=u.card(l.name,`${l.quantity} purchased at ${l.unit_cents} cents`,l.id);c.append(u.form([['quantity','Return quantity','number'],['reference','Return reference']],'Request return',v=>u.action('RequestReturn',{line_id:l.id,quantity:Number(v.quantity),reference:v.reference},'Return requested')));u.workspace.append(c);
    for(const r of l.returns){const item=u.card(r.reference,`${r.status}; ${r.quantity} units; refunded ${r.refunds.reduce((a,b)=>a+b,0)} cents`,r.id);if(r.status==='requested')for(const accepted of [true,false])item.append(u.button(accepted?'Accept inspection':'Reject inspection',()=>u.action('InspectReturn',{return_id:r.id,accepted},'Inspection recorded')));if(r.status==='approved')item.append(u.button('Issue refund',()=>u.action('RefundReturn',{return_id:r.id},'Refund issued')));u.workspace.append(item);}}
};

renderers.garden_plan=async u=>{
  const b=(await u.walker('GardenBoard'))[0];u.workspace.append(u.element('h2','Garden plots and crop rotation'));
  for(const plot of b.plots){const c=u.card(plot.name,`${plot.area} area; ${plot.plantings.filter(p=>p.status==='growing').reduce((s,p)=>s+p.area,0)} growing area`,plot.id);
    const f=u.form([['area','Planting area','number']],'Plant crop',v=>u.action('PlantCrop',{plot_id:plot.id,crop_id:v.crop_id,area:Number(v.area)},'Crop planted'));u.select(f,'crop_id','Crop',b.crops.map(c=>[c.id,c.name]));c.append(f);u.workspace.append(c);
    for(const [index,p]of plot.plantings.entries()){const item=u.card(`${plot.name} ${p.crop} planting ${index+1}`,`${p.status}; harvest ${p.harvest}`,p.id);
      for(const t of p.tasks){item.append(u.element('p',`${t.name}: ${t.done?'done':'pending'}`));if(!t.done)item.append(u.button('Complete '+t.name,()=>u.action('CompleteTask',{task_id:t.id},'Garden task completed')));}
      if(p.status==='growing')item.append(u.form([['quantity','Harvest quantity','number']],'Record harvest',v=>u.action('HarvestPlanting',{planting_id:p.id,quantity:Number(v.quantity)},'Harvest recorded')));u.workspace.append(item);}
  }
};

renderers.tournament=async u=>{
  const b=(await u.walker('BracketBoard'))[0];u.workspace.append(u.element('h2','Tournament brackets'));
  u.workspace.append(u.form([['name','Tournament name']],'Create tournament',v=>u.action('CreateTournament',v,'Tournament created')));
  for(const t of b.tournaments)for(const round of t.rounds)for(const m of round.matches){const c=u.card(`${t.name} round ${round.number} match ${m.position}`,`${m.home} vs ${m.away}; winner ${m.winner||'pending'}`,m.id);
    if(!m.winner)c.append(u.form([['home_score','Home score','number'],['away_score','Away score','number']],'Record score',v=>u.action('ScoreMatch',{match_id:m.id,home_score:Number(v.home_score),away_score:Number(v.away_score)},'Score recorded')));u.workspace.append(c);}
};

renderers.incident_room=async u=>{
  const b=(await u.walker('IncidentBoard'))[0];u.workspace.append(u.element('h2','Service impact and incident response'));
  for(const s of b.services){const c=u.card(s.name,`Depends on ${s.dependencies.length} services`,s.id);c.append(u.form([['summary','Incident summary']],'Open incident',v=>u.action('OpenIncident',{service_id:s.id,...v},'Incident opened')));u.workspace.append(c);}
  for(const i of b.incidents){const c=u.card(i.summary,i.status,i.id);for(const a of i.alerts){c.append(u.element('p',`${a.service}: ${a.acknowledged?'acknowledged':'unacknowledged'}`));if(!a.acknowledged)c.append(u.button('Acknowledge '+a.service,()=>u.action('AcknowledgeAlert',{alert_id:a.id},'Alert acknowledged')));}
    for(const a of i.actions){c.append(u.element('p',`${a.name}: ${a.done?'done':'pending'}`));if(!a.done)c.append(u.button('Complete '+a.name,()=>u.action('CompleteAction',{action_id:a.id},'Incident action completed')));}
    if(i.status==='open')c.append(u.form([['name','Action name']],'Add action',v=>u.action('AddAction',{incident_id:i.id,...v},'Action added')),u.button('Resolve incident',()=>u.action('ResolveIncident',{incident_id:i.id},'Incident resolved')));u.workspace.append(c);}
};
