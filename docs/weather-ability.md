# Weather Ability real provider test

Weather Ability uses `mock` by default. To test real weather data with
OpenWeather, set the provider in `config.json` and provide the API key through
the environment only.

```json
{
  "weather": {
    "provider": "openweather",
    "fallback_to_mock": true,
    "openweather_lang": "kr"
  }
}
```

```powershell
$env:OPENWEATHER_API_KEY="your-api-key"
python -m unittest tests.test_abilities
```

The OpenWeather integration test is skipped unless `OPENWEATHER_API_KEY` is
present. API keys must not be committed. OpenWeather current weather calls use
`units=metric` and `lang=kr`; OpenWeather documents `kr` as the Korean language
code for the `lang` parameter.

