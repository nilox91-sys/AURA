import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import test_integrations as integration
import test_app as base
from ai_engine import LLMEngine,ProviderState,REPLY_SCHEMA
from extended_ai import call_extra,discover
from provider_registry import PROVIDERS


class ServiceChoiceTests(unittest.TestCase):
    setUp=integration.IntegrationTests.setUp

    def test_full_catalog_can_be_opened_without_changing_model_or_secrets(self):
        model='gemini:gemini-3.1-flash-lite'
        self.manager.update({'model':model,'ai_model_allowlist':[model],'gemini_api_key':'keep-secret'})
        response=self.client.post('/api/integrations/selection',json={'mode':'all'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.manager.get('ai_model_allowlist'),[])
        self.assertEqual(self.manager.get('model'),model)
        self.assertEqual(self.manager.get('gemini_api_key'),'keep-secret')

    def test_keep_selected_requires_generation_success_for_same_model_and_key(self):
        self.manager.update({'model':'openai:gpt-test','openai_api_key':'first-key'})
        with patch.object(LLMEngine,'health',ProviderState()):
            self.assertEqual(self.client.post('/api/integrations/selection',json={'mode':'selected'}).status_code,409)
            keys=LLMEngine.provider_keys(self.manager.get_all())
            LLMEngine.health.catalog_success('openai',keys,['gpt-test'])
            self.assertEqual(self.client.post('/api/integrations/selection',json={'mode':'selected'}).status_code,409)
            LLMEngine.health.success('openai',keys,model='gpt-other')
            self.assertEqual(self.client.post('/api/integrations/selection',json={'mode':'selected'}).status_code,409)
            LLMEngine.health.success('openai',keys,model='gpt-test')
            self.assertEqual(self.client.post('/api/integrations/selection',json={'mode':'selected'}).status_code,200)
            self.assertEqual(self.manager.get('ai_model_allowlist'),['openai:gpt-test'])
            self.manager.update({'openai_api_key':'second-key'})
            self.assertEqual(self.client.post('/api/integrations/selection',json={'mode':'selected'}).status_code,409)

    def test_paid_providers_are_never_automatic_fallbacks(self):
        settings={**self.manager.get_all(),'allow_fallback':True,'xai_api_key':'paid','cerebras_api_key':'credits'}
        self.assertFalse(any(p in {'xai','cerebras','openai','anthropic','deepseek','mistral'} for p,m in LLMEngine.provider_candidates('auto:free',settings)))

    def test_cerebras_uses_compatible_chat_and_bounded_reasoning(self):
        with patch('extended_ai.request_json',return_value={'choices':[{'message':{'content':'ok'},'finish_reason':'stop'}]}) as remote:
            text,incomplete,_=call_extra('cerebras','qwen-3.8-27b',[{'role':'user','content':'test'}],{'cerebras_api_key':'private'},
                {'max_tokens':512,'reasoning_effort':'low'},REPLY_SCHEMA)
        args=remote.call_args.args
        self.assertEqual(args[1],'https://api.cerebras.ai/v1/chat/completions')
        self.assertEqual(args[2]['Authorization'],'Bearer private')
        self.assertEqual(args[3]['reasoning_effort'],'low');self.assertEqual(args[3]['max_tokens'],512)
        self.assertEqual(text,'ok');self.assertFalse(incomplete)

    def test_xai_uses_responses_without_server_storage_or_tool_access(self):
        data={'output':[{'type':'message','content':[{'type':'output_text','text':'ok'}]}],'status':'completed'}
        with patch('extended_ai.request_json',return_value=data) as remote:
            result=call_extra('xai','grok-test',[{'role':'user','content':'test'}],{'xai_api_key':'private'},{'max_tokens':512},REPLY_SCHEMA)
        args=remote.call_args.args
        self.assertEqual(args[1],'https://api.x.ai/v1/responses')
        self.assertFalse(args[3]['store']);self.assertNotIn('tools',args[3])
        self.assertEqual(args[3]['text']['format']['schema'],REPLY_SCHEMA)
        self.assertEqual(result[0],'ok')

    def test_new_catalogs_require_credentials_and_exclude_media(self):
        for provider in ('xai','cerebras'):
            with patch('extended_ai.request_json') as remote:
                self.assertEqual(discover(provider,{})['state'],'not_configured')
                remote.assert_not_called()
        with patch('extended_ai.request_json',return_value={'data':[{'id':'grok-test'},{'id':'grok-imagine-video'},{'id':'grok-voice'}]}) as remote:
            self.assertEqual(discover('xai',{'xai_api_key':'private'})['models'],['grok-test'])
        self.assertEqual(remote.call_args.args[1],'https://api.x.ai/v1/models')

    def test_openrouter_labels_actual_model_pricing_without_guessing(self):
        data={'data':[{'id':'vendor/free','pricing':{'prompt':'0','completion':'0'}},
                      {'id':'vendor/paid','pricing':{'prompt':'0.00001','completion':'0.00002'}},
                      {'id':'vendor/request-fee','pricing':{'prompt':'0','completion':'0','request':'0.01'}},
                      {'id':'vendor/unknown'},{'id':'vendor/invalid','pricing':{'prompt':'NaN','completion':'0'}}]}
        with patch('extended_ai.request_json',return_value=data):result=discover('openrouter',{'openrouter_api_key':'private'})
        self.assertEqual(result['model_costs'],{'openrouter/free':'free','vendor/free':'free','vendor/paid':'paid','vendor/request-fee':'paid'})
        self.assertIn('vendor/unknown',result['models']);self.assertNotIn('vendor/unknown',result['model_costs'])


class ServiceChoicePageTests(unittest.TestCase):
    setUp=base.JarvisTests.setUp

    def test_new_users_get_full_choice_and_can_filter_service_plans(self):
        page=self.client.get('/settings').get_data(as_text=True)
        self.assertIn('id="service-plan-filter"',page)
        self.assertIn('id="keep-selected-model"',page)
        self.assertIn('data-tiers="paid"',page)
        self.assertIn('<option value="cerebras"',page);self.assertIn('<option value="xai"',page)
        self.assertEqual(len(self.client.get('/api/providers').json['providers']),13)
        self.assertEqual(set(PROVIDERS),{item['id'] for item in self.client.get('/api/providers').json['providers']})

    def test_existing_personal_selection_is_preserved_with_an_explicit_full_catalog_button(self):
        model='gemini:gemini-3.1-flash-lite'
        base.jarvis.settings_manager.update({'model':model,'ai_model_allowlist':[model]})
        page=self.client.get('/settings').get_data(as_text=True)
        self.assertIn('id="show-all-providers"',page)
        self.assertNotIn('id="service-plan-filter"',page)
        self.assertNotIn('<option value="xai"',page)
        self.assertEqual(base.jarvis.settings_manager.get('ai_model_allowlist'),[model])

    def test_new_credentials_are_private_and_empty_values_keep_saved_keys(self):
        base.jarvis.settings_manager.update({'xai_api_key':'xai-private','cerebras_api_key':'cerebras-private'})
        for path in ('/settings','/api/providers','/api/status'):
            data=self.client.get(path).data
            self.assertNotIn(b'xai-private',data);self.assertNotIn(b'cerebras-private',data)
        response=self.client.post('/api/save_settings',json={'xai_api_key':'','cerebras_api_key':''})
        self.assertEqual(response.status_code,200)
        self.assertEqual(base.jarvis.settings_manager.get('xai_api_key'),'xai-private')

if __name__=='__main__':unittest.main()
