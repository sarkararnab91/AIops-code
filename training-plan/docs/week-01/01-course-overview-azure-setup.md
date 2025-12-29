# Session 1: Course Overview & Azure Setup

## 📋 Session Details
- **Duration**: 1 hour
- **Week**: 1, Day 1 (Monday)
- **Prerequisites**: Azure subscription, VS Code installed
- **Deliverable**: Resource group with proper tags, Azure CLI configured

---

## 🎯 Learning Objectives

By the end of this session, you will:
1. Understand the AIOps evolution journey (Traditional → ML → AgentOps)
2. Set up your Azure development environment
3. Create a tagged resource group for the training
4. Understand cost optimization strategies

---

## 📚 Concepts

### What is AIOps?

**AIOps (Artificial Intelligence for IT Operations)** is the application of AI and machine learning to automate and enhance IT operations processes.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         THE AIOPS EVOLUTION                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   1990s-2000s          2010s              2020s              2024+          │
│   ┌─────────┐      ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │
│   │ Manual  │  →   │ Rule-Based  │  → │  ML-Based   │  → │  AgentOps   │   │
│   │ ITOps   │      │ Automation  │    │   AIOps     │    │ (LLM+MCP)   │   │
│   └─────────┘      └─────────────┘    └─────────────┘    └─────────────┘   │
│                                                                              │
│   • Manual logs     • Threshold        • Anomaly          • Natural lang   │
│   • Phone calls       alerts             detection        • RAG knowledge  │
│   • War rooms       • Scripts          • Prediction       • Auto-remediate │
│   • Tribal          • Runbooks         • Correlation      • Tool calling   │
│     knowledge                          • Noise reduction  • Self-healing   │
│                                                                              │
│   MTTR: Hours       MTTR: 30-60min     MTTR: 15-30min     MTTR: <10min     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Our Training Journey

| Week | Focus | Key Technologies |
|------|-------|------------------|
| 1-2 | Traditional Monitoring | Azure Monitor, App Insights, Log Analytics |
| 3-4 | ML-Based AIOps | Isolation Forest, Prophet, scikit-learn |
| 5-7 | AgentOps with MCP | Azure OpenAI, MCP, RAG, ChromaDB |
| 8 | Capstone | Chaos Engineering, Value Demonstration |

### Cost Optimization Strategy

We use several techniques to keep Azure costs low:

1. **Serverless-first**: Cosmos DB serverless, Container Apps scale-to-zero
2. **Free tiers**: Azure Monitor (5GB/month), Log Analytics (5GB/month)
3. **Auto-shutdown**: Resources stop at 7 PM daily
4. **Resource tagging**: Easy identification and cleanup
5. **One-command teardown**: Delete everything instantly when done

---

## 🛠️ Hands-On Exercise

### Step 1: Install Required Tools

```bash
# Install Azure CLI (if not already installed)
# macOS
brew install azure-cli

# Windows (PowerShell as Admin)
winget install Microsoft.AzureCLI

# Linux (Ubuntu/Debian)
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

### Step 2: Login to Azure

```bash
# Login to Azure
az login

# List available subscriptions
az account list --output table

# Set your subscription (replace with your subscription name or ID)
az account set --subscription "Your-Subscription-Name"

# Verify current subscription
az account show --output table
```

### Step 3: Install uv (Python Package Manager)

We use `uv` for fast, reliable Python package management:

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify installation
uv --version
```

### Step 4: Create Resource Group with Tags

```bash
# Define variables
RESOURCE_GROUP="aiops-training-rg"
LOCATION="eastus"
TODAY=$(date +%Y-%m-%d)
DELETE_AFTER=$(date -v+60d +%Y-%m-%d)  # 60 days from now

# Create resource group with cost optimization tags
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION \
  --tags \
    Project="aiops-training" \
    Environment="training" \
    Owner="your-name" \
    AutoShutdown="true" \
    CostCenter="aiops-lab" \
    CreatedDate="$TODAY" \
    DeleteAfter="$DELETE_AFTER" \
    Purpose="AIOps Training Lab"

# Verify resource group was created
az group show --name $RESOURCE_GROUP --output table
```

### Step 5: Clone/Initialize Training Repository

```bash
# Navigate to your workspace
cd ~/projects  # or your preferred directory

# Create training directory structure
mkdir -p aiops-training
cd aiops-training

# Initialize with uv
uv init

# Copy pyproject.toml from training materials (or create new)
# The pyproject.toml has all dependencies pre-configured

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
uv sync
```

### Step 6: Verify Setup

```bash
# Check Azure CLI
az --version

# Check Python environment
python --version
which python

# Check key packages
python -c "import fastapi; print(f'FastAPI: {fastapi.__version__}')"
python -c "import pandas; print(f'Pandas: {pandas.__version__}')"
python -c "import sklearn; print(f'scikit-learn: {sklearn.__version__}')"

# List resource group tags
az group show --name aiops-training-rg --query tags
```

---

## 🧪 Verification Checklist

Before moving to the next session, ensure you have:

- [ ] Azure CLI installed and logged in
- [ ] Correct subscription selected
- [ ] Resource group `aiops-training-rg` created with all tags
- [ ] uv installed
- [ ] Python virtual environment created
- [ ] Dependencies installed successfully

---

## 📖 Key Takeaways

1. **AIOps is an evolution**, not a revolution - we build on traditional monitoring
2. **Cost optimization is critical** for training environments
3. **Resource tagging** enables easy management and cleanup
4. **uv** provides fast, reliable Python environment management

---

## 🔜 Next Session Preview

**Session 2: AKS Deployment with Scale-to-Zero**
- Deploy Azure Kubernetes Service cluster
- Configure autoscaling for cost optimization
- Understand Kubernetes basics for our microservices

---

## 📚 Additional Resources

- [Azure CLI Documentation](https://docs.microsoft.com/en-us/cli/azure/)
- [AIOps Gartner Definition](https://www.gartner.com/en/information-technology/glossary/aiops)
- [uv Documentation](https://github.com/astral-sh/uv)
- [Azure Cost Management](https://docs.microsoft.com/en-us/azure/cost-management-billing/)
