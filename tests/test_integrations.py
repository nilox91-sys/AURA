import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from extended_ai import call_extra,discover
from ai_engine import LLMEngine,REPLY_SCHEMA
from settings_store import SettingsManager,SECRET_KEYS
from preferences import EXTRA_DEFAULTS
from settings_api import register_settings_api
from github_auth import GithubAccount


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.manager=SettingsManager(self.root/'settings.json',{**EXTRA_DEFAULTS,'model':'openrouter:openrouter/free','assistant_name':'AURA',
            'ollama_host':'http://localhost:11434','openrouter_api_key':'','groq_api_key':'','hf_api_key':'','gemini_api_key':''})
        self.app=Flask('test',template_folder=str(Path(__file__).resolve().parents[1]/'templates'))
        self.app.config['TESTING']=True
        self.auth=GithubAccount(self.app,self.manager,self.root)
        register_settings_api(self.app,self.manager,self.manager.defaults,self.root)
        self.client=self.app.test_client()

    def test_native_openai_responses_schema_and_no_storage(self):
        result={'model':'gpt-4.1-mini','output':[{'type':'message','content':[{'type':'output_text','text':'ciao'}]}]}
        with patch('extended_ai.request_json',return_value=result) as remote:
            text,incomplete,_=call_extra('openai','gpt-4.1-mini',[{'role':'user','content':'hi'}],{'openai_api_key':'test'}, {'max_tokens':512},REPLY_SCHEMA)
        payload=remote.call_args.args[3]
        self.assertFalse(payload['store']);self.assertEqual(payload['text']['format']['schema'],REPLY_SCHEMA)
        self.assertNotIn('response_format',payload);self.assertEqual(text,'ciao');self.assertFalse(incomplete)

    def test_claude_separates_system_and_detects_truncation(self):
        with patch('extended_ai.request_json',return_value={'content':[{'type':'text','text':'ok'}],'stop_reason':'max_tokens'}) as remote:
            text,incomplete,_=call_extra('anthropic','claude-test',[{'role':'system','content':'style'},{'role':'user','content':'hi'}],{'anthropic_api_key':'test'},{'max_tokens':512},REPLY_SCHEMA)
        args=remote.call_args.args
        self.assertEqual(args[3]['system'],'style');self.assertEqual(len(args[3]['messages']),1)
        self.assertEqual(args[2]['x-api-key'],'test');self.assertTrue(incomplete)

    def test_local_and_custom_local_never_use_cloud_fallback(self):
        for provider in ('lmstudio','compatible'):
            settings={**self.manager.get_all(),'allow_fallback':True,'openai_api_key':'paid','groq_api_key':'remote'}
            self.assertEqual(LLMEngine.provider_candidates(provider+':local',settings),[(provider,'local')])
        candidates=LLMEngine.provider_candidates('auto:free',{**self.manager.get_all(),'openai_api_key':'paid','anthropic_api_key':'paid'})
        self.assertFalse(any(p in {'openai','anthropic','mistral','deepseek'} for p,m in candidates))

    def test_catalog_and_probe_do_not_send_preferences(self):
        self.manager.update({'openai_api_key':'private','user_bio':'my-private-bio'})
        with patch('settings_api.discover',return_value={'id':'openai','state':'available','models':['gpt-test'],'message':'ok'}):
            self.assertEqual(self.client.post('/api/integrations/check',json={'provider':'openai'}).status_code,200)
        with patch.object(LLMEngine,'call_provider',return_value='{"testo":"ok","emozione":"normale"}') as call:
            response=self.client.post('/api/integrations/test',json={'provider':'openai','model':'gpt-test'})
            self.assertNotIn('my-private-bio',json.dumps(call.call_args.args[2]));self.assertEqual(response.status_code,200)

    def test_keys_export_remove_and_validation(self):
        self.manager.update({'openai_api_key':'private','custom_instructions':'Prima un esempio.\nPoi i dettagli.'})
        self.manager.update({'openai_api_key':''});self.assertEqual(self.manager.get('openai_api_key'),'private')
        exported=self.client.get('/api/preferences/export');self.assertNotIn(b'private',exported.data)
        self.assertFalse(SECRET_KEYS.intersection(exported.json['preferences']))
        self.assertNotIn('github_client_id',exported.json['preferences'])
        self.assertEqual(self.client.post('/api/integrations/remove-key',json={'provider':'openai'}).status_code,200)
        self.assertEqual(self.manager.get('openai_api_key'),'')
        for values in ({'lmstudio_host':'http://example.com/v1'},{'compatible_base_url':'https://key:secret@example.com/v1'},
                       {'tts_cache_mb':1},{'theme':'bad'},{'custom_instructions':'x'*3001}):
            with self.assertRaises(ValueError):self.manager.update(values)

    def test_cache_clear_only_removes_hash_audio(self):
        (self.root/('a'*64+'.wav')).write_bytes(b'audio');(self.root/'important.wav').write_bytes(b'keep')
        self.assertEqual(self.client.get('/api/audio-cache').json['files'],1)
        self.client.post('/api/audio-cache',json={});self.assertTrue((self.root/'important.wav').exists())

    def start_flow(self):
        self.manager.update({'github_client_id':'Iv1.test'})
        with patch.object(self.auth,'github',return_value={'device_code':'server-secret','user_code':'ABCD-EFGH','expires_in':900,'interval':5}):
            response=self.client.post('/api/github/start',json={})
        self.assertNotIn(b'server-secret',response.data)
        with self.client.session_transaction() as state:flow_id=state['github_flow']
        self.auth.flows[flow_id]['next']=0
        return flow_id

    def test_github_device_flow_uses_no_secret_or_repo_scope_and_discards_token(self):
        flow=self.start_flow()
        with patch.object(self.auth,'github',side_effect=[{'access_token':'ephemeral-secret'},{'id':123,'login':'tester','name':'Test'}]) as remote:
            response=self.client.post('/api/github/poll',json={})
        self.assertEqual(response.json['state'],'authenticated')
        self.assertNotIn(b'ephemeral-secret',response.data)
        for path in self.root.rglob('*'):
            if path.is_file():self.assertNotIn(b'ephemeral-secret',path.read_bytes())
        self.assertEqual(remote.call_args_list[0].kwargs['data']['grant_type'],'urn:ietf:params:oauth:grant-type:device_code')
        self.assertNotIn('client_secret',remote.call_args_list[0].kwargs['data'])
        self.assertNotIn(flow,self.auth.flows)
        self.assertTrue(self.client.get('/api/github/status').json['authenticated'])
        self.assertFalse(self.app.test_client().get('/api/github/status').json['authenticated'])

    def test_github_throttle_slowdown_expiry_and_cross_browser(self):
        flow=self.start_flow()
        with patch.object(self.auth,'github',return_value={'error':'slow_down'}) as remote:
            self.assertEqual(self.client.post('/api/github/poll',json={}).json['interval'],10)
            self.client.post('/api/github/poll',json={});self.assertEqual(remote.call_count,1)
        self.assertEqual(self.app.test_client().post('/api/github/poll',json={}).status_code,410)
        self.auth.flows[flow]['expires']=0
        self.assertEqual(self.client.post('/api/github/poll',json={}).status_code,410)

    def test_github_lock_requires_original_owner_and_blocks_api(self):
        self.start_flow();self.auth.owner_path.write_text('{"id":100,"login":"owner"}')
        self.manager.update({'github_require_login':True})
        self.assertEqual(self.client.get('/api/preferences/export').status_code,401)
        with patch.object(self.auth,'github',side_effect=[{'access_token':'private'},{'id':200,'login':'other'}]):
            self.assertEqual(self.client.post('/api/github/poll',json={}).status_code,403)
        self.assertEqual(self.auth.owner()['id'],100)
        self.assertEqual(self.client.get('/settings').status_code,302)
        self.assertEqual(self.client.get('/login').status_code,200)

    def test_github_network_error_is_redacted(self):
        self.manager.update({'github_client_id':'Iv1.test'})
        import requests
        with patch.object(self.auth,'github',side_effect=requests.ConnectionError('private-token')):
            response=self.client.post('/api/github/start',json={})
        self.assertEqual(response.status_code,503);self.assertNotIn(b'private-token',response.data)

    def test_personalization_and_current_neapolitan_survive_history(self):
        settings={**self.manager.get_all(),'dialect':'napoletano','dialect_intensity':'authentic','personality_profile':'mentor',
                  'custom_instructions':'Spiega con esempi di videogiochi','communication_tone':'warm','emoji_style':'occasional'}
        messages,_=LLMEngine.build_messages('Spiega la cache',[],settings)
        self.assertIn('Spiega con esempi di videogiochi',messages[0]['content'])
        self.assertIn('prevalentemente napoletano',messages[-2]['content'])

if __name__=='__main__':unittest.main()
