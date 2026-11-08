#!/usr/bin/env python3
"""Read-only, no-network Chromium replay for Repo_Dex and optional Atlas.

Run after installing Python Playwright + Chromium:
  python3 qa/replay_review_keyboard.py --atlas ../Westkitty_Atlas/index.html
The public feed is read from docs/feed/latest.json by default; no GitHub API
requests are made. In local workbenches an adjacent feed_sample.json may be used.
This is a browser-runtime fixture, not proof of hosted Pages navigation.
"""
import argparse
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
PARSER = argparse.ArgumentParser()
PARSER.add_argument('--feed', type=Path, default=REPO / 'docs/feed/latest.json')
PARSER.add_argument('--atlas', type=Path, default=ROOT / 'Westkitty_Atlas/index.html')
args = PARSER.parse_args()
feed_file = args.feed if args.feed.is_file() else ROOT / 'feed_sample.json'
if not feed_file.is_file():
    raise SystemExit('Provide --feed PATH to a validated public Repo_Dex feed snapshot')
feed = json.loads(feed_file.read_text(encoding='utf-8'))
assert feed['schema'] == 'repo-dex-feed/v1' and feed['source']['visibility'] == 'public-only'
assert len(feed['opportunities']) >= 22, 'Need at least 22 synthetic or source-grounded candidates for pagination replay'
# Presentation-only synthetic capability duplicates, never published as claims.
if len(feed.get('capability_genomes') or []) < 25:
    ev = feed['opportunities'][0]['evidence'][0]
    feed['capability_genomes'] = [{
        'repository_id': ev['repository_id'], 'kind': 'test-declaration',
        'statement': f'Synthetic QA declaration {i}', 'token': f'fixture-{i}',
        'evidence_level': 'described', 'freshness': 'sampled-head',
        'constraint': 'TEST FIXTURE: not a verified capability', 'source': ev,
    } for i in range(26)]
receipt = {
    'schema':'repo-dex-scan-status/v1','owner':'westkitty','state':'success',
    'latest_feed_digest':feed['content_sha256'],
    'feed_generated_at':feed['generated_at'],
    'last_successful_scan':feed['generated_at'],
    'public_repositories':len(feed['repositories']),
}
def safe_json(value):
    return json.dumps(value, ensure_ascii=False).replace('<', '\\u003c')

def assert_focus(page,selector,message):
    focused = page.locator(selector).evaluate('(el)=>el===document.activeElement')
    if not focused:
        value = page.evaluate('document.activeElement?.outerHTML.slice(0,220)')
        raise AssertionError(f'{message}: focus is on {value}')

def lab_html():
    html = (REPO / 'docs/laboratory.html').read_text(encoding='utf-8')
    js = (REPO / 'docs/shared-decisions.js').read_text(encoding='utf-8')
    old = '<script src="./shared-decisions.js"></script>'
    assert html.count(old) == 1
    html = html.replace(old, '<script>'+js+'</script>')
    script = '<script>window.fetch=async()=>new Response(JSON.stringify('+safe_json(feed)+'),{status:200,headers:{"Content-Type":"application/json"}});</script>'
    return html.replace('</head>',script+'</head>',1)

def atlas_html():
    html = args.atlas.read_text(encoding='utf-8')
    old = "if(location.protocol==='https:'&&location.hostname==='westkitty.github.io')refreshLiveFeed();"
    old_hosted = "const hosted=location.protocol==='https:'&&location.hostname==='westkitty.github.io';"
    assert old in html and old_hosted in html, 'Expected hosted guards changed; update test fixture without changing shipped guard'
    html=html.replace(old,'if(true)refreshLiveFeed();').replace(old_hosted,'const hosted=true;')
    mock = '<script>window.fetch=async(url)=>new Response(JSON.stringify(String(url).includes("status.json")?'+safe_json(receipt)+':'+safe_json(feed)+'),{status:200,headers:{"Content-Type":"application/json"}});</script>'
    return html.replace('<script type="application/json" id="constellation-data">',mock+'<script type="application/json" id="constellation-data">',1)

passed = 0
def check(name, fun):
    global passed
    fun()
    passed+=1
    print('PASS:',name)

with sync_playwright() as play:
    chromium = os.environ.get('CHROMIUM_PATH') or ('/usr/bin/chromium' if Path('/usr/bin/chromium').is_file() else None)
    launch = {'headless': True}
    if chromium:
        launch['executable_path'] = chromium
    browser = play.chromium.launch(**launch)
    lab=browser.new_page(viewport={'width':1250,'height':880})
    errors=[]
    lab.on('pageerror',lambda error:errors.append(str(error)))
    lab.set_content(lab_html(),wait_until='load')
    lab.wait_for_timeout(200)
    check('Laboratory feed loaded',lambda:(_ for _ in ()).throw(AssertionError('Feed did not load')) if lab.locator('#findings article').count()!=8 else None)
    lab.locator('#findings article:first-child .actions button').filter(has_text='Investigate').click()
    check('Laboratory decision retains focus',lambda:assert_focus(lab,'#findings article:first-child .actions button.choice[aria-pressed=true]','Decision'))
    lab.locator('#findings article:first-child .actions button').filter(has_text='Shelve').click()
    check('Filtered-out decision moves focus to filter',lambda:assert_focus(lab,'#filter','After shelving'))
    lab.locator('#filter').select_option('all')
    lab.locator('#reviewMore').click()
    check('Review pagination focuses first revealed card',lambda:assert_focus(lab,'#findings article:nth-child(9) h3','Review pagination'))
    lab.locator('#capMore').click()
    check('Capability pagination focuses first revealed source',lambda:assert_focus(lab,'#cap-list .cap-record:nth-child(13) summary','Capability pagination'))
    while lab.locator('#findings article').count() < 22:
        lab.locator('#reviewMore').click()
    older=lab.locator('#findings article:nth-child(20)')
    old_id=older.get_attribute('id')
    older.locator('.actions button').filter(has_text='Reject').click()
    lab.locator('#filter').select_option('unresolved')
    lab.locator('#query').fill('unmatched-private-token')
    lab.locator('#decision-history .decision-entry a').filter(has_text='Open this review').first.click()
    check('History reopens item past page eight',lambda:assert_focus(lab,'#'+old_id,'History target'))
    check('History clears prior search/filter',lambda:(_ for _ in ()).throw(AssertionError('Filters not cleared')) if lab.locator('#filter').input_value()!='all' or lab.locator('#query').input_value() else None)
    check('Laboratory no JavaScript exceptions',lambda:(_ for _ in ()).throw(AssertionError(str(errors))) if errors else None)
    lab.close()
    if args.atlas.is_file():
        atlas=browser.new_page(viewport={'width':1280,'height':800})
        errs=[]
        atlas.on('pageerror',lambda error:errs.append(str(error)))
        atlas.set_content(atlas_html(),wait_until='load')
        atlas.wait_for_timeout(200)
        atlas.locator('#taskExplore').click()
        atlas.get_by_role('button',name='Text index').first.click()
        atlas.get_by_role('button',name='Show next 40').click()
        check('Atlas text-index page retains keyboard focus',lambda:assert_focus(atlas,'.index-entry:nth-child(41)','Text index'))
        atlas.locator('#taskReview').click()
        atlas.locator('.review-card:first-child .review-controls button').filter(has_text='Investigate').click()
        check('Atlas private decision retains focus',lambda:assert_focus(atlas,'.review-card:first-child .review-controls button[aria-pressed=true]','Atlas decision'))
        atlas.locator('.review-card:first-child .review-controls button').filter(has_text='Shelve').click()
        check('Atlas removed candidate moves focus to status filter',lambda:assert_focus(atlas,'.review-toolbar select','Atlas filtered candidate'))
        atlas.get_by_role('button',name='Review history').first.click()
        check('Atlas Review history stays keyboard reachable',lambda:assert_focus(atlas,'.review-actions button:has-text("Review history")','Atlas history'))
        atlas.get_by_role('button',name='Investigation shortlist').first.click()
        check('Atlas shortlist stays keyboard reachable',lambda:assert_focus(atlas,'.review-actions button:has-text("Investigation shortlist")','Atlas shortlist'))
        atlas.get_by_role('button',name='Review history').first.click()
        atlas.get_by_role('button',name='Show 8 more candidates').click()
        check('Atlas review paging focuses new candidate',lambda:assert_focus(atlas,'.review-card:nth-child(9) h3','Atlas pagination'))
        check('Atlas no JavaScript exceptions',lambda:(_ for _ in ()).throw(AssertionError(str(errs))) if errs else None)
        atlas.close()
    browser.close()
print(f'PASS: {passed} focus/history/pagination browser checks; controlled in-memory feed, not public-site navigation')
