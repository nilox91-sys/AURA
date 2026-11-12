import json,time,unittest
from unittest.mock import patch
import requests
from ai_engine import LLMEngine,ProviderState
from extended_ai import discover,request_json
from provider_errors import ProviderHTTPError,describe_error


def failure(code,payload=None,headers=None):
    response=requests.Response();response.status_code=code;response._content=json.dumps(payload or {}).encode()
    if headers:response.headers.update(headers)
    return requests.HTTPError('private-key-never-show-this',response=response)


class ProviderFailureTests(unittest.TestCase):
    def test_payment_required_is_account_wide_and_catalog_does_not_hide_it(self):
        state=ProviderState();keys={'huggingface':'secret'}
        state.failure('huggingface',keys,'one',failure(402,{'error':'Purchase pre-paid credits'}))
        self.assertEqual(state.blocked('huggingface',keys,'two')['kind'],'balance')
        state.catalog_success('huggingface',keys,['one','two'])
        status=state.status('huggingface',keys,'two')
        self.assertEqual(status['kind'],'balance');self.assertFalse(status['generation_verified'])
        state.success('huggingface',keys,model='two')
        self.assertTrue(state.status('huggingface',keys,'two')['generation_verified'])

    def test_openrouter_daily_quota_uses_reset_and_blocks_all_free_models(self):
        reset=time.time()+7200
        error=failure(429,{'error':{'message':'Rate limit exceeded: free-models-per-day','metadata':{'headers':{'X-RateLimit-Reset':str(int(reset*1000))}}}})
        state=ProviderState();keys={'openrouter':'private'}
        state.failure('openrouter',keys,'openrouter/free',error)
        status=state.status('openrouter',keys,'another:free')
        self.assertEqual(status['kind'],'daily_quota');self.assertGreater(status['retry_after'],7100)
        self.assertIn('reset_at',status);self.assertNotIn('private',json.dumps(status))

    def test_model_retirement_suggests_only_an_identifier_without_raw_message(self):
        detail=describe_error('gemini',failure(404,{'error':{'message':'private-key-never-show-this: Please update your code to use models/gemini-3.5-flash-lite for the latest features.'}}))
        self.assertEqual(detail['suggested_model'],'gemini-3.5-flash-lite')
        self.assertNotIn('private-key-never-show-this',json.dumps(detail))

    def test_groq_network_denial_and_overload_are_actionable(self):
        detail=describe_error('groq',failure(403,{'error':{'message':'Access denied. Please check your network settings.'}}))
        self.assertEqual(detail['kind'],'network_denied');self.assertIn('rete',detail['message'])
        self.assertEqual(describe_error('gemini',failure(503))['kind'],'overloaded')

    def test_failure_for_one_model_does_not_label_another_model_as_broken(self):
        state=ProviderState();keys={'gemini':'secret'}
        state.failure('gemini',keys,'overloaded',failure(503))
        self.assertEqual(state.status('gemini',keys,'working')['state'],'unchecked')
        state.success('gemini',keys,model='working')
        self.assertTrue(state.status('gemini',keys,'working')['generation_verified'])
        self.assertFalse(state.status('gemini',keys,'another')['generation_verified'])

    def test_gemini_lite_uses_minimal_thinking_and_respects_longer_request_budget(self):
        from ai_engine import generation_options
        from runtime_utils import provider_deadline
        options=generation_options.set({'max_tokens':1024,'reasoning_effort':'low'})
        deadline=provider_deadline.set(time.monotonic()+50)
        try:
            with patch('ai_engine.requests.post') as post:
                post.return_value.json.return_value={'candidates':[{'content':{'parts':[{'text':'ok'}]}}]}
                self.assertEqual(LLMEngine.call_gemini('private','gemini-3.1-flash-lite',[{'role':'user','content':'hi'}]),'ok')
            self.assertEqual(post.call_args.kwargs['json']['generationConfig']['thinkingConfig'],{'thinkingLevel':'minimal'})
            self.assertEqual(post.call_args.kwargs['timeout'][1],40)
        finally:
            generation_options.reset(options);provider_deadline.reset(deadline)

    def test_catalog_filters_non_chat_models_and_ranks_working_default(self):
        data={'models':[{'name':'models/'+name,'supportedGenerationMethods':['generateContent']} for name in (
            'gemini-2.5-flash','gemini-3.5-flash-lite','gemini-3.8-flash-tts','lyria-3.5','deep-research-preview','gemini-3.1-flash-image')]}
        with patch('extended_ai.request_json',return_value=data):
            result=discover('gemini',{'gemini_api_key':'secret'})
        self.assertEqual(result['models'],['gemini-3.5-flash-lite','gemini-2.5-flash'])

    def test_bounded_http_transport_retains_error_details_after_closing_response(self):
        response=requests.Response();response.status_code=402;response._content=b'{"error":{"message":"Insufficient Balance"}}';response._content_consumed=True
        with patch('extended_ai.requests.Session') as factory:
            factory.return_value.__enter__.return_value.request.return_value.__enter__.return_value=response
            with self.assertRaises(ProviderHTTPError) as caught:request_json('POST','https://api.deepseek.com/chat/completions')
        self.assertEqual(describe_error('deepseek',caught.exception)['kind'],'balance')

    def test_unverified_ollama_is_not_an_automatic_dead_end(self):
        with patch.dict('os.environ',{'GROQ_API_KEY':'','GEMINI_API_KEY':'','OPENROUTER_API_KEY':'','HF_API_KEY':''}):
            old=LLMEngine.health;LLMEngine.health=ProviderState()
            try:
                self.assertEqual(LLMEngine.provider_candidates('auto:free',{'allow_fallback':True}),[])
                self.assertEqual(LLMEngine.provider_candidates('ollama:my-model',{'allow_fallback':True}),[('ollama','my-model')])
            finally:LLMEngine.health=old

if __name__=='__main__':unittest.main()
