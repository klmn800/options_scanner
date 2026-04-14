# AI Council Framework

A sophisticated system for creating specialized AI personalities with distinct expertise, behaviors, and model preferences. Perfect for getting diverse perspectives on complex trading and technical decisions.

## 🎭 Quick Start

### Test the Demo Personality
```bash
# Single question to demo personality
python ai_council/personalities/demo_guru.py "What do you think about selling puts on NVDA?"

# Interactive session
python ai_council/personalities/demo_guru.py
```

### Council Discussion
```bash
# Full council discussion (all personalities)
python ai_council/council.py "Should I hedge my portfolio?" --full-council

# Specific personalities
python ai_council/council.py "Is NVDA vol too high?" --members demo_guru,risk_hawk

# List available personalities
python ai_council/council.py --list-personalities
```

## 🏗️ Creating Your Own Personalities

### Step 1: Copy the Template
```bash
cp ai_council/personalities/personality_template.py ai_council/personalities/your_personality.py
```

### Step 2: Choose Your Model
Pick from available models in `ai_council/models/`:

**Claude Models** (anthropic_interface.py):
- `claude-3-5-sonnet-20241022` - Most capable, excellent for analysis
- `claude-3-opus-20240229` - Most powerful, complex reasoning
- `claude-3-haiku-20240307` - Fastest, cost-effective

**GPT Models** (openai_interface.py):
- `gpt-4o` - Latest with vision capabilities  
- `gpt-4o-mini` - Efficient, great value
- `gpt-3.5-turbo` - Fast, cost-effective

**Local Models** (ollama_interface.py):
- `llama3.1` - Powerful local model
- `deepseek-coder` - Excellent for coding tasks
- `mistral` - Efficient general purpose

**Gemini Models** (google_interface.py):
- `gemini-1.5-pro` - Massive 2M token context
- `gemini-1.5-flash` - Fast with 1M context

**Grok Models** (xai_interface.py):
- `grok-2` - Latest with real-time info
- `grok-2-mini` - Efficient version

### Step 3: Fill in Your Personality
```python
class YourTrader(BasePersonality):
    name = "John 'Volatility King' Smith"
    code_name = "vol_king"
    specialty = "Volatility Trading"
    
    primary_model = "claude-3-5-sonnet-20241022"
    backup_model = "gpt-4o-mini" 
    
    system_prompt = '''You are John Smith, known as the "Volatility King"...
    [Detailed personality description]
    '''
```

### Step 4: Test Your Personality
```bash
python ai_council/personalities/vol_king.py "Test question"
```

## 🎯 Usage Examples

### Individual Personality Consultation
```bash
# Get risk analysis
python ai_council/personalities/risk_hawk.py "I'm thinking of selling naked calls on TSLA"

# Options strategy advice  
python ai_council/personalities/options_guru.py "Iron condor vs butterfly on SPY before earnings?"

# Technical analysis
python ai_council/personalities/chart_wizard.py "SPY breaking resistance, what's next?"
```

### Multi-Personality Council Discussions
```bash
# Market outlook discussion
python ai_council/council.py "What's your 2024 market outlook?" --full-council --rounds 2

# Strategy evaluation
python ai_council/council.py "Evaluate this wheel strategy on AAPL" \
  --members options_guru,risk_hawk,macro_analyst \
  --context "AAPL at $180, selling $170 puts weekly"

# Save important discussions
python ai_council/council.py "Should I close my positions before FOMC?" --save
```

### Interactive Council Session
```bash
python ai_council/council.py --interactive

# Set your preferred council members
[Council] >>> members risk_hawk,options_guru,macro_analyst

# Add context for better responses
[Council] >>> context Portfolio: 60% stocks, 30% options, 10% cash. Risk tolerance: moderate

# Ask questions naturally
[Council] >>> What do you think about the current VIX level?
```

## 🔧 Programming Integration

### Use in Your Python Code
```python
from ai_council import get_personality

# Get a specific personality
risk_expert = get_personality('risk_hawk')
advice = risk_expert.ask("Evaluate this portfolio risk")

# Council discussion
from ai_council.council import AICouncil
council = AICouncil()
discussion = council.discuss(
    question="Should I hedge gamma exposure?",
    members=['options_guru', 'risk_hawk'],
    context="Portfolio delta-neutral but high gamma"
)
```

### Oracle Integration
```python
# Use in your existing Oracle system
def get_ai_council_opinion(question, context=""):
    council = AICouncil()
    discussion = council.discuss(question, context=context)
    return discussion['responses']
```

## 📁 Directory Structure

```
ai_council/
├── __init__.py              # Main imports and utilities
├── base_personality.py      # Base class for all personalities  
├── council.py               # Multi-personality orchestrator
├── personalities/
│   ├── personality_template.py    # Template for creating new personalities
│   ├── demo_guru.py              # Working example personality
│   └── [your_personalities.py]   # Your custom personalities
├── models/
│   ├── anthropic_interface.py    # Claude models
│   ├── openai_interface.py       # GPT models  
│   ├── ollama_interface.py       # Local models
│   ├── google_interface.py       # Gemini models
│   └── xai_interface.py          # Grok models
└── discussions/             # Saved council discussions (auto-created)
```

## 🔑 API Key Setup

Add your API keys to `config.json`:

```json
{
  "claude_api": {
    "api_key": "your-anthropic-key"
  },
  "openai_api": {
    "api_key": "your-openai-key"
  },
  "google_ai": {
    "api_key": "your-google-ai-key" 
  },
  "xai_api": {
    "api_key": "your-xai-key"
  }
}
```

Or use environment variables:
```bash
export ANTHROPIC_API_KEY="your-key"
export OPENAI_API_KEY="your-key"
export GOOGLE_AI_API_KEY="your-key"
export XAI_API_KEY="your-key"
```

## 🎨 Personality Design Tips

### Rich Personalities Work Better
- **Detailed backstory**: "Started trading in the 2008 crash..."
- **Specific expertise**: List 5-7 concrete skills
- **Behavioral traits**: How do they think and react?
- **Signature phrases**: What do they always say?
- **Decision framework**: Their step-by-step process

### System Prompt Best Practices  
- **Identity first**: "You are [Name], a [Role] with [Experience]"
- **Expertise areas**: What they know deeply
- **Thinking style**: How they approach problems  
- **Communication style**: Formal? Casual? Technical jargon?
- **Specific behaviors**: What makes them unique?

### Model Selection Strategy
- **Claude**: Best for analysis, reasoning, complex tasks
- **GPT**: Good all-around, reliable, fast
- **Local (Ollama)**: Private, free, but requires setup
- **Gemini**: Massive context windows for long discussions
- **Grok**: Unique perspective, real-time info

## 🚀 Advanced Features

### Conversation History
Personalities remember your conversation within a session:
```bash
python ai_council/personalities/demo_guru.py
[Guru] >>> What's IV rank on NVDA?
[You] >>> It's at 85th percentile
[Guru] >>> Given that high IV rank, what strategies make sense?
# The guru remembers the 85th percentile context
```

### Pre/Post Processing
Customize how personalities handle input/output:
```python
def pre_process_query(self, query):
    # Add domain context
    return f"From a risk management perspective: {query}"

def post_process_response(self, response):
    # Add warnings or formatting
    return response + "\n⚠️ Always check your risk limits!"
```

### Council Rounds
Multi-round discussions where personalities respond to each other:
```bash
python ai_council/council.py "Market crash coming?" --rounds 3 --full-council
# Round 1: Initial responses
# Round 2: Responses considering others' input  
# Round 3: Final synthesis
```

## 🎯 Suggested Personalities for Trading

**Essential Council Members:**
1. **Risk Manager** - "What could go wrong?"
2. **Options Specialist** - "Let's look at the Greeks"  
3. **Technical Analyst** - "Charts are showing..."
4. **Macro Economist** - "Fed policy suggests..."
5. **Market Psychologist** - "Sentiment indicates..."
6. **Quant Researcher** - "The data shows..."

**Specialized Experts:**
- **Volatility Trader** - IV analysis and vol strategies
- **Flow Analyst** - Dark pool and institutional activity
- **Sector Specialist** - Deep knowledge of specific industries
- **International Trader** - Global markets and currency impacts
- **Crypto Native** - Digital assets and DeFi protocols

Start with 2-3 core personalities and expand your council as needed!

## 🤝 Contributing

This framework is designed to be extended. Create personalities that would be valuable to the trading community and share them!

Happy trading with your AI Council! 🎭📈