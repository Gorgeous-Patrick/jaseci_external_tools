"""Independent domain oracles for the remaining full applications."""
from scenarios import Scenario

READERS = {'recipe_pantry': 'PantryBoard', 'trip_board': 'Itinerary', 'delivery_route':'RouteBoard', 'hiring_pipeline':'HiringBoard', 'sales_pipeline':'SalesBoard', 'grant_review':'ReviewBoard'}
READERS.update(lab_samples='LabBoard',asset_care='AssetBoard')
READERS.update(utility_meter='MeterBoard',volunteer_shift='VolunteerBoard',poll_assembly='AssemblyBoard')
READERS.update(budget_ledger='BudgetBoard',build_release='ReleaseBoard',knowledge_map='KnowledgeBoard')
READERS.update(return_counter='ReturnBoard',garden_plan='GardenBoard',tournament='BracketBoard',incident_room='IncidentBoard')


def begin(server, token, seed, directory, reader):
    case = Scenario(server, token, directory)
    case.call('Seed', {'seed': seed})
    board = case.call(reader, read=True)
    case.call('Seed', {'seed': seed})
    assert case.call(reader, read=True) == board, 'Seed must be idempotent'
    return case, board


def recipe_pantry(server, token, seed, directory):
    c, b = begin(server, token, seed, directory, 'PantryBoard')
    recipes = {r['name']: r['id'] for r in b['recipes']}
    assert len(b['ingredients']) == 3 and len(recipes) == 2
    meal = c.call('PlanMeal', {'recipe_id': recipes['Breakfast porridge'], 'name': 'Breakfast', 'servings': 4})['meal_id']
    pancake = c.call('PlanMeal', {'recipe_id': recipes['Pancakes'], 'name': 'Lunch', 'servings': 2})['meal_id']
    before = c.call('PantryBoard', read=True)
    c.call('CookMeal', {'meal_id': meal}, False)
    assert c.call('PantryBoard', read=True) == before
    shopping = c.call('ShoppingList', read=True)
    assert {r['name']: (r['required'], r['shortage']) for r in shopping} == {
        'Rolled oats': (8, 3-seed%3), 'Milk': (6, 4), 'Flour': (6, 0)}
    c.call('BuyIngredient', {'ingredient_id': b['ingredients'][0]['id'], 'quantity': 0}, False)
    for r in shopping:
        if r['shortage']: c.call('BuyIngredient', {'ingredient_id': r['id'], 'quantity': r['shortage']})
    c.call('CookMeal', {'meal_id': meal}); c.call('CookMeal', {'meal_id': meal}, False)
    c.call('CookMeal', {'meal_id': pancake})
    c.assert_private('PantryBoard', 'ingredients', 'CookMeal', {'meal_id': meal})
    result = c.finish('PantryBoard')
    for i in result['expected_board']['ingredients']:
        assert i['units'] == 0 and i['initial'] + i['purchased'] == i['units'] + i['consumed']
    return result


def trip_board(server, token, seed, directory):
    c, b = begin(server, token, seed, directory, 'Itinerary')
    j = b['journeys'][0]; lodge = j['stops'][0]
    assert len(j['stops']) == 2 and lodge['capacity'] == 4+seed%3
    c.call('AddStop', {'journey_id': j['id'], 'name': 'Invalid', 'day': 4}, False)
    stop = c.call('AddStop', {'journey_id': j['id'], 'name': 'Observatory', 'day': 2})['stop_id']
    booking = c.call('ReserveStay', {'stop_id': lodge['id'], 'guests': 2})['booking_id']
    c.call('ReserveStay', {'stop_id': lodge['id'], 'guests': lodge['capacity']}, False)
    c.call('CancelStay', {'booking_id': booking}); c.call('CancelStay', {'booking_id': booking}, False)
    c.call('MoveStop', {'stop_id': stop, 'position': 0}, False)
    c.call('MoveStop', {'stop_id': stop, 'position': 1}, False)
    c.call('MoveStop', {'stop_id': stop, 'position': 2})
    c.assert_private('Itinerary', 'journeys', 'ReserveStay', {'stop_id': stop, 'guests': 1})
    result = c.finish('Itinerary'); rows = result['expected_board']['journeys'][0]['stops']
    assert [s['name'] for s in rows] == ['Lakeside lodge', 'Observatory', 'Museum visit']
    assert [s['position'] for s in rows] == [1,2,3] and all(s['booked'] == 0 for s in rows)
    return result


SCENARIOS = {'recipe_pantry': recipe_pantry, 'trip_board': trip_board}


def delivery_route(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'RouteBoard'); r=b['routes'][0]; parcels={p['label']:p['id'] for p in b['parcels']}
    c.call('LoadRoute',{'route_id':r['id']},False)
    for name in ['Sensors','Cables']: c.call('AssignParcel',{'route_id':r['id'],'parcel_id':parcels[name]})
    c.call('AssignParcel',{'route_id':r['id'],'parcel_id':parcels['Spare crate']},False)
    c.call('DeliveryAttempt',{'route_id':r['id']},False)
    c.call('LoadRoute',{'route_id':r['id']}); c.call('LoadRoute',{'route_id':r['id']},False)
    c.call('DeliveryAttempt',{'route_id':r['id'],'success':False,'note':'No recipient'})
    c.call('DeliveryAttempt',{'route_id':r['id']},False)
    stops=c.call('RouteBoard',read=True)['routes'][0]['stops']; assert [s['status'] for s in stops]==['failed','pending']
    c.call('RetryStop',{'stop_id':stops[0]['id']}); c.call('DeliveryAttempt',{'route_id':r['id']}); c.call('DeliveryAttempt',{'route_id':r['id']})
    c.call('DeliveryAttempt',{'route_id':r['id']},False)
    tiny=c.call('CreateRoute',{'name':'Tiny route','capacity':1})['route_id']
    c.call('AssignParcel',{'route_id':tiny,'parcel_id':parcels['Spare crate']},False)
    c.assert_private('RouteBoard','depots','LoadRoute',{'route_id':r['id']})
    result=c.finish('RouteBoard'); board=result['expected_board']; assert board['routes'][0]['complete']
    assert next(p for p in board['parcels'] if p['label']=='Sensors')['scans']==['loaded','failed','retried','delivered']
    return result


def hiring_pipeline(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'HiringBoard'); runtime,advocate=b['jobs']; avery,morgan=b['candidates']
    def apply(job,candidate): return c.call('ApplyJob',{'job_id':job['id'],'candidate_id':candidate['id']})['application_id']
    def score(app,values):
        for round,value in zip(['technical','collaboration'],values):
            i=c.call('ScheduleInterview',{'application_id':app,'round':round})['interview_id']
            c.call('ScoreInterview',{'interview_id':i,'score':6},False); c.call('ScoreInterview',{'interview_id':i,'score':value})
            c.call('ScoreInterview',{'interview_id':i,'score':value},False)
    app=apply(runtime,avery); c.call('OfferApplication',{'application_id':app},False)
    c.call('ApplyJob',{'job_id':runtime['id'],'candidate_id':avery['id']},False)
    score(app,[5,4]); c.call('OfferApplication',{'application_id':app})
    other=apply(runtime,morgan); score(other,[5,5]); c.call('OfferApplication',{'application_id':other},False)
    shared=apply(advocate,avery); score(shared,[5,5]); c.call('OfferApplication',{'application_id':shared},False)
    c.assert_private('HiringBoard','jobs','OfferApplication',{'application_id':app})
    result=c.finish('HiringBoard'); assert sum(a['status']=='offered' for j in result['expected_board']['jobs'] for a in j['applications'])==1
    return result

SCENARIOS.update(delivery_route=delivery_route,hiring_pipeline=hiring_pipeline)


def sales_pipeline(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'SalesBoard'); o=b['accounts'][0]['opportunities'][0]
    c.call('QualifyOpportunity',{'opportunity_id':o['id']},False)
    c.call('CreateQuote',{'opportunity_id':o['id'],'quantity':1,'unit_cents':100},False)
    c.call('LogActivity',{'opportunity_id':o['id'],'note':'Discussed renewal'})
    c.call('QualifyOpportunity',{'opportunity_id':o['id']})
    c.call('CloseWon',{'opportunity_id':o['id']},False)
    c.call('CreateQuote',{'opportunity_id':o['id'],'quantity':0,'unit_cents':100},False)
    q=c.call('CreateQuote',{'opportunity_id':o['id'],'quantity':3,'unit_cents':12000})['quote_id']
    c.call('AcceptQuote',{'quote_id':q});c.call('AcceptQuote',{'quote_id':q},False);c.call('CloseWon',{'opportunity_id':o['id']})
    c.call('LogActivity',{'opportunity_id':o['id'],'note':'Edit closed deal'},False)
    c.assert_private('SalesBoard','accounts','CloseWon',{'opportunity_id':o['id']})
    r=c.finish('SalesBoard');assert r['expected_board']['won_cents']==36000;return r


def grant_review(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'ReviewBoard'); p=b['proposals'][0]; alex,blair,cameron=b['reviewers']
    c.call('AssignReviewer',{'proposal_id':p['id'],'reviewer_id':alex['id']},False)
    assignments=[]
    for reviewer in [blair,cameron]:
        a=c.call('AssignReviewer',{'proposal_id':p['id'],'reviewer_id':reviewer['id']})['assignment_id'];assignments.append(a)
        c.call('AssignReviewer',{'proposal_id':p['id'],'reviewer_id':reviewer['id']},False)
    c.call('ReleaseProposal',{'proposal_id':p['id']},False)
    c.call('SubmitReview',{'assignment_id':assignments[0],'merit':6,'feasibility':3},False)
    c.call('SubmitReview',{'assignment_id':assignments[0],'merit':4,'feasibility':3})
    c.call('SubmitReview',{'assignment_id':assignments[0],'merit':5,'feasibility':5},False)
    c.call('SubmitReview',{'assignment_id':assignments[1],'merit':5,'feasibility':4})
    c.call('ReleaseProposal',{'proposal_id':p['id']})
    c.assert_private('ReviewBoard','proposals','ReleaseProposal',{'proposal_id':p['id']})
    r=c.finish('ReviewBoard');assert r['expected_board']['proposals'][0]['score_total']==25 and r['expected_board']['proposals'][0]['released'];return r

SCENARIOS.update(sales_pipeline=sales_pipeline,grant_review=grant_review)


def lab_samples(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'LabBoard');s=b['samples'][0];batch=b['batches'][0];assay=b['assays'][0]
    c.call('SplitSample',{'sample_id':s['id'],'volume':200},False)
    ids=[c.call('SplitSample',{'sample_id':s['id'],'volume':v})['aliquot_id'] for v in [30,20]]
    for a in ids:c.call('AddAliquot',{'batch_id':batch['id'],'aliquot_id':a})
    c.call('AddAliquot',{'batch_id':batch['id'],'aliquot_id':ids[0]},False)
    c.call('ReleaseBatch',{'batch_id':batch['id']},False)
    for a,v in zip(ids,[15,25]):c.call('RecordResult',{'aliquot_id':a,'assay_id':assay['id'],'value':v})
    c.call('ReleaseBatch',{'batch_id':batch['id']},False)
    c.call('RecordResult',{'aliquot_id':ids[1],'assay_id':assay['id'],'value':15})
    c.call('ReleaseBatch',{'batch_id':batch['id']});c.call('RecordResult',{'aliquot_id':ids[1],'assay_id':assay['id'],'value':15},False)
    c.assert_private('LabBoard','samples','SplitSample',{'sample_id':s['id'],'volume':1})
    r=c.finish('LabBoard');s=r['expected_board']['samples'][0];assert s['remaining']+sum(a['volume'] for a in s['aliquots'])==s['initial'] and r['expected_board']['batches'][0]['released'];return r


def asset_care(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'AssetBoard');a=b['assets'][0];part=b['parts'][0];tech=b['technicians'][0]
    c.call('InspectAsset',{'asset_id':a['id'],'issue':'Minor wear','severity':2})
    c.call('OpenWorkOrder',{'asset_id':a['id'],'technician_id':tech['id']},False)
    c.call('InspectAsset',{'asset_id':a['id'],'issue':'Seal failure','severity':4})
    order=c.call('OpenWorkOrder',{'asset_id':a['id'],'technician_id':tech['id']})['order_id']
    c.call('OpenWorkOrder',{'asset_id':a['id'],'technician_id':tech['id']},False)
    c.call('FinishWorkOrder',{'order_id':order},False)
    c.call('ConsumePart',{'order_id':order,'part_id':part['id'],'quantity':6},False)
    c.call('ConsumePart',{'order_id':order,'part_id':part['id'],'quantity':2});c.call('FinishWorkOrder',{'order_id':order})
    c.call('ConsumePart',{'order_id':order,'part_id':part['id'],'quantity':1},False)
    c.assert_private('AssetBoard','assets','FinishWorkOrder',{'order_id':order})
    r=c.finish('AssetBoard');assert r['expected_board']['parts'][0]['stock']==3 and r['expected_board']['assets'][0]['status']=='operational';return r

SCENARIOS.update(lab_samples=lab_samples,asset_care=asset_care)


def utility_meter(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'MeterBoard');m=b['meters'][0];last=m['readings'][-1]
    c.call('AddReading',{'meter_id':m['id'],'value':100},False)
    c.call('CorrectReading',{'reading_id':last['id'],'value':1160})
    assert c.call('BillMeter',{'meter_id':m['id']})['cents']==500
    c.call('BillMeter',{'meter_id':m['id']},False);c.call('CorrectReading',{'reading_id':last['id'],'value':1161},False)
    new=c.call('AddReading',{'meter_id':m['id'],'value':1170})['reading_id'];c.call('CorrectReading',{'reading_id':new,'value':1180})
    assert c.call('BillMeter',{'meter_id':m['id']})['cents']==40
    c.assert_private('MeterBoard','buildings','BillMeter',{'meter_id':m['id']})
    r=c.finish('MeterBoard');assert sum(i['cents'] for i in r['expected_board']['meters'][0]['invoices'])==540;return r


def volunteer_shift(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'VolunteerBoard');s=b['shifts'][0];volunteers={v['name']:v['id'] for v in b['volunteers']}
    c.call('JoinShift',{'shift_id':s['id'],'volunteer_id':volunteers['Morgan']},False)
    joined={}
    for name,status in [('Avery','confirmed'),('Jordan','waitlisted'),('Casey','waitlisted')]:
        a=c.call('JoinShift',{'shift_id':s['id'],'volunteer_id':volunteers[name]});assert a['status']==status;joined[name]=a['signup_id']
    c.call('JoinShift',{'shift_id':s['id'],'volunteer_id':volunteers['Avery']},False)
    c.call('CancelSignup',{'signup_id':joined['Jordan']});c.call('CancelSignup',{'signup_id':joined['Avery']});c.call('CancelSignup',{'signup_id':joined['Avery']},False)
    c.assert_private('VolunteerBoard','organizations','CancelSignup',{'signup_id':joined['Casey']})
    r=c.finish('VolunteerBoard');a=r['expected_board']['shifts'][0]['signups'];assert [x['volunteer'] for x in a if x['status']=='confirmed']==['Casey'];return r


def poll_assembly(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'AssemblyBoard');m=b['motions'][0];yes,no=m['options'];avery,morgan,guest=b['voters']
    c.call('CloseMotion',{'motion_id':m['id']},False)
    c.call('CastBallot',{'motion_id':m['id'],'voter_id':guest['id'],'option_id':yes['id']},False)
    c.call('CastBallot',{'motion_id':m['id'],'voter_id':avery['id'],'option_id':b['motions'][1]['options'][0]['id']},False)
    for voter,option in [(avery,yes),(morgan,no),(avery,no)]:c.call('CastBallot',{'motion_id':m['id'],'voter_id':voter['id'],'option_id':option['id']})
    c.call('CloseMotion',{'motion_id':m['id']});c.call('CastBallot',{'motion_id':m['id'],'voter_id':avery['id'],'option_id':yes['id']},False)
    c.assert_private('AssemblyBoard','assemblies','CloseMotion',{'motion_id':m['id']})
    r=c.finish('AssemblyBoard');m=r['expected_board']['motions'][0];assert m['outcome']=='rejected' and m['ballot_count']==2 and [o['votes'] for o in m['options']]==[0,2];return r

SCENARIOS.update(utility_meter=utility_meter,volunteer_shift=volunteer_shift,poll_assembly=poll_assembly)


def budget_ledger(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'BudgetBoard');equip,travel=b['envelopes'];cat=b['categories'][0]
    c.call('AllocateBudget',{'envelope_id':equip['id'],'amount':200000},False)
    for e,amount in [(equip,40000),(travel,20000)]:c.call('AllocateBudget',{'envelope_id':e['id'],'amount':amount})
    c.call('SpendEnvelope',{'envelope_id':equip['id'],'category_id':cat['id'],'amount':15000})
    c.call('TransferBudget',{'source_id':equip['id'],'target_id':equip['id'],'amount':1,'reference':'INVALID'},False)
    tx={'source_id':equip['id'],'target_id':travel['id'],'amount':5000,'reference':'MOVE-1'};c.call('TransferBudget',tx);c.call('TransferBudget',tx,False)
    c.call('SpendEnvelope',{'envelope_id':equip['id'],'category_id':cat['id'],'amount':30000},False)
    c.assert_private('BudgetBoard','budgets','AllocateBudget',{'envelope_id':equip['id'],'amount':1})
    r=c.finish('BudgetBoard');b=r['expected_board'];assert all(e['balance']==sum(x['amount'] for x in e['entries']) for e in b['envelopes']);spent=-sum(x['amount'] for e in b['envelopes'] for x in e['entries'] if x['kind']=='expense')
    assert spent==15000 and b['budgets'][0]['unallocated']+sum(e['balance'] for e in b['envelopes'])+spent==b['budgets'][0]['initial'];return r


def build_release(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'ReleaseBoard');r=b['releases'][0]
    build=c.call('CreateBuild',{'release_id':r['id'],'label':'Native build'})['build_id']
    checks={x['name']:x['id'] for x in c.call('ReleaseBoard',read=True)['releases'][0]['builds'][0]['checks']}
    c.call('DeployBuild',{'build_id':build},False);c.call('RecordCheck',{'check_id':checks['integration'],'passed':True},False)
    for name in ['unit','integration','security']:c.call('RecordCheck',{'check_id':checks[name],'passed':True})
    c.call('RecordCheck',{'check_id':checks['unit'],'passed':False});c.call('DeployBuild',{'build_id':build},False)
    current=c.call('ReleaseBoard',read=True)['releases'][0]['builds'][0];assert [x['status'] for x in current['checks']]==['failed','pending','pending']
    for name in ['unit','integration','security']:c.call('RecordCheck',{'check_id':checks[name],'passed':True})
    c.call('DeployBuild',{'build_id':build,'environment':'production'});c.call('DeployBuild',{'build_id':build},False)
    c.call('RecordCheck',{'check_id':checks['unit'],'passed':False},False)
    c.assert_private('ReleaseBoard','releases','DeployBuild',{'build_id':build})
    result=c.finish('ReleaseBoard');assert result['expected_board']['releases'][0]['builds'][0]['deployments']==['production'];return result


def knowledge_map(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'KnowledgeBoard');a,other,last=b['articles']
    c.call('PublishArticle',{'article_id':a['id']},False)
    c.call('ReviewRevision',{'revision_id':a['revisions'][0]['id'],'note':'Initial review'})
    new=c.call('ReviseArticle',{'article_id':a['id'],'body':'Revised graph storage design'})['revision_id'];c.call('PublishArticle',{'article_id':a['id']},False)
    c.call('ReviewRevision',{'revision_id':new,'note':'Reviewed new version'});c.call('PublishArticle',{'article_id':a['id']})
    for source,target in [(a,other),(other,a),(a,other)]:c.call('LinkArticles',{'source_id':source['id'],'target_id':target['id']})
    c.call('LinkArticles',{'source_id':a['id'],'target_id':a['id']},False)
    assert sorted(c.call('ExploreLinks',{'article_id':a['id']},read=True))==sorted([a['title'],other['title']])
    c.assert_private('KnowledgeBoard','articles','PublishArticle',{'article_id':a['id']})
    r=c.finish('KnowledgeBoard');assert r['expected_board']['articles'][0]['published_revision']==2 and len(r['expected_board']['articles'][0]['links'])==1;return r

SCENARIOS.update(budget_ledger=budget_ledger,build_release=build_release,knowledge_map=knowledge_map)


def return_counter(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'ReturnBoard');l=b['orders'][0]['lines'][0]
    c.call('RequestReturn',{'line_id':l['id'],'quantity':4,'reference':'EXCESS'},False)
    rejected=c.call('RequestReturn',{'line_id':l['id'],'quantity':1,'reference':'REJECTED'})['return_id']
    c.call('RefundReturn',{'return_id':rejected},False);c.call('InspectReturn',{'return_id':rejected,'accepted':False});c.call('RefundReturn',{'return_id':rejected},False)
    accepted=c.call('RequestReturn',{'line_id':l['id'],'quantity':2,'reference':'ACCEPTED'})['return_id']
    c.call('InspectReturn',{'return_id':accepted,'accepted':True});assert c.call('RefundReturn',{'return_id':accepted})['cents']==2*l['unit_cents']
    c.call('RefundReturn',{'return_id':accepted},False);c.call('RequestReturn',{'line_id':l['id'],'quantity':2,'reference':'EXCESS-2'},False)
    c.assert_private('ReturnBoard','orders','RefundReturn',{'return_id':accepted})
    r=c.finish('ReturnBoard');assert sum(x['quantity'] for x in r['expected_board']['orders'][0]['lines'][0]['returns'] if x['status']!='rejected')==2;return r


def garden_plan(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'GardenBoard');plot=b['plots'][0];tomato,bean=b['crops']
    p=c.call('PlantCrop',{'plot_id':plot['id'],'crop_id':tomato['id'],'area':8})['planting_id']
    c.call('PlantCrop',{'plot_id':plot['id'],'crop_id':bean['id'],'area':5},False)
    c.call('HarvestPlanting',{'planting_id':p,'quantity':12},False)
    tasks=c.call('GardenBoard',read=True)['plots'][0]['plantings'][0]['tasks']
    for t in tasks:c.call('CompleteTask',{'task_id':t['id']})
    c.call('CompleteTask',{'task_id':tasks[0]['id']},False);c.call('HarvestPlanting',{'planting_id':p,'quantity':12})
    c.call('PlantCrop',{'plot_id':plot['id'],'crop_id':tomato['id'],'area':1},False)
    c.call('PlantCrop',{'plot_id':plot['id'],'crop_id':bean['id'],'area':5})
    c.assert_private('GardenBoard','plots','HarvestPlanting',{'planting_id':p,'quantity':1})
    r=c.finish('GardenBoard');rows=r['expected_board']['plots'][0]['plantings'];assert rows[0]['harvest']==12 and sum(x['area'] for x in rows if x['status']=='growing')==5;return r


def tournament(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'BracketBoard');t=b['tournaments'][0];semi=t['rounds'][0]['matches'];final=t['rounds'][1]['matches'][0]
    c.call('ScoreMatch',{'match_id':final['id'],'home_score':1,'away_score':0},False)
    c.call('ScoreMatch',{'match_id':semi[0]['id'],'home_score':1,'away_score':1},False)
    for m,home,away in [(semi[0],2,1),(semi[1],0,3),(final,1,2)]:c.call('ScoreMatch',{'match_id':m['id'],'home_score':home,'away_score':away})
    c.call('ScoreMatch',{'match_id':semi[0]['id'],'home_score':0,'away_score':1},False)
    c.assert_private('BracketBoard','tournaments','ScoreMatch',{'match_id':final['id'],'home_score':1,'away_score':0})
    r=c.finish('BracketBoard');f=r['expected_board']['tournaments'][0]['rounds'][1]['matches'][0];assert f['home']=='Aster' and f['away']=='Delta' and f['winner']=='Delta' and len(f['results'])==1;return r


def incident_room(server,token,seed,directory):
    c,b=begin(server,token,seed,directory,'IncidentBoard');service=next(s for s in b['services'] if s['name']=='Database')
    incident=c.call('OpenIncident',{'service_id':service['id'],'summary':'Native outage'})['incident_id']
    current=c.call('IncidentBoard',read=True)['incidents'][0]
    assert sorted(a['service'] for a in current['alerts'])==['API','Cache','Database']
    c.call('ResolveIncident',{'incident_id':incident},False)
    for a in current['alerts']:c.call('AcknowledgeAlert',{'alert_id':a['id']})
    c.call('ResolveIncident',{'incident_id':incident},False)
    extra=c.call('AddAction',{'incident_id':incident,'name':'Restore service'})['action_id']
    for a in [current['actions'][0]['id'],extra]:c.call('CompleteAction',{'action_id':a})
    c.call('ResolveIncident',{'incident_id':incident});c.call('AddAction',{'incident_id':incident,'name':'Edit closed'},False)
    c.assert_private('IncidentBoard','services','ResolveIncident',{'incident_id':incident})
    r=c.finish('IncidentBoard');assert r['expected_board']['incidents'][0]['status']=='resolved';return r

SCENARIOS.update(return_counter=return_counter,garden_plan=garden_plan,tournament=tournament,incident_room=incident_room)


def verify_browser(app, server, token):
    b = server.walker(READERS[app], {}, token)[0]
    if app == 'recipe_pantry':
        assert next(m for m in b['meals'] if m['name'] == 'Browser breakfast')['status'] == 'cooked'
        assert all(i['initial'] + i['purchased'] == i['units'] + i['consumed'] for i in b['ingredients'])
    elif app == 'trip_board':
        s = next(s for s in b['journeys'][0]['stops'] if s['name'] == 'Browser garden')
        assert s['booked'] == 2 and s['day'] == 2
    elif app=='delivery_route':
        r=next(r for r in b['routes'] if r['name']=='Browser route'); assert r['complete'] and len(r['stops'])==1
        assert next(p for p in b['parcels'] if p['label']=='Spare crate')['scans']==['loaded','failed','retried','delivered']
    elif app=='hiring_pipeline':
        a=next(a for j in b['jobs'] for a in j['applications'] if a['candidate']=='Browser Candidate')
        assert a['status']=='offered' and [i['scores'] for i in a['interviews']]==[[5],[5]]
    elif app=='sales_pipeline':
        o=next(o for a in b['accounts'] for o in a['opportunities'] if o['title']=='Browser expansion');assert o['stage']=='won' and o['amount_cents']==50000 and b['won_cents']==86000
    elif app=='grant_review':
        p=next(p for p in b['proposals'] if p['title']=='Compiler verification');assert p['released'] and p['score_total']==30 and p['review_count']==2
    elif app=='lab_samples':
        batch=next(x for x in b['batches'] if x['name']=='Browser batch');assert batch['released'] and len(batch['aliquots'])==1
        assert all(s['initial']==s['remaining']+sum(a['volume'] for a in s['aliquots']) for s in b['samples'])
    elif app=='asset_care':
        a=next(a for a in b['assets'] if a['name']=='Valve V1');assert a['status']=='operational' and a['orders'][0]['status']=='closed'
        assert b['parts'][0]['stock']==2
    elif app=='utility_meter':assert sum(i['cents'] for m in b['meters'] for i in m['invoices'])==580
    elif app=='volunteer_shift':assert [x['volunteer'] for x in b['shifts'][0]['signups'] if x['status']=='confirmed']==['Avery']
    elif app=='poll_assembly':
        m=next(m for m in b['motions'] if m['title']=='Release vote');assert m['outcome']=='passed' and m['ballot_count']==2
    elif app=='budget_ledger':
        spent=-sum(x['amount'] for e in b['envelopes'] for x in e['entries'] if x['kind']=='expense');assert spent==16000 and sum(t['reference']=='BROWSER-TRANSFER' for t in b['transfers'])==1
        assert b['budgets'][0]['unallocated']+sum(e['balance'] for e in b['envelopes'])+spent==b['budgets'][0]['initial']
    elif app=='build_release':
        build=next(x for r in b['releases'] for x in r['builds'] if x['label']=='Browser build');assert build['status']=='deployed' and build['deployments']==['staging']
    elif app=='knowledge_map':
        a=next(a for a in b['articles'] if a['title']=='Release handbook');assert a['published_revision']==2 and a['revisions'][-1]['body']=='Browser research note'
    elif app=='return_counter':
        r=next(r for o in b['orders'] for l in o['lines'] for r in l['returns'] if r['reference']=='BROWSER-RETURN');assert r['status']=='refunded' and r['refunds']==[400]
    elif app=='garden_plan':
        p=next(p for p in b['plots'] if p['name']=='South bed')['plantings'][0];assert p['status']=='harvested' and p['harvest']==3 and all(t['done'] for t in p['tasks'])
    elif app=='tournament':
        t=next(t for t in b['tournaments'] if t['name']=='Browser cup');assert t['rounds'][1]['matches'][0]['winner']=='Cedar'
    elif app=='incident_room':
        i=next(i for i in b['incidents'] if i['summary']=='Browser outage');assert i['status']=='resolved' and len(i['alerts'])==3 and all(a['acknowledged'] for a in i['alerts']) and all(a['done'] for a in i['actions'])
    else:
        raise ValueError('No browser oracle for ' + app)
