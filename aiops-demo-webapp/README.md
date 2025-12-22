# AIOps Demo Dashboard - Azure Static Web App

A modern, interactive web application demonstrating enterprise monitoring concepts, Service Level Indicators (SLIs), Service Level Objectives (SLOs), and AIOps principles for Azure training.

## 🎯 Purpose

This webapp illustrates how enterprises use observability tools to monitor services and respond to incidents. It's designed to work with Azure Application Insights and shows the difference between traditional static threshold alerts and AI-powered dynamic threshold alerting.

## 📋 Features

### Dashboard Metrics
- **Service Health**: Real-time status, uptime, and response time
- **Performance Metrics**: Request rate, error rate, and CPU usage
- **SLI & SLO Tracking**: Availability indicators and SLO targets
- **Dependencies**: Database, cache, and API gateway status
- **Active Alerts**: Static and dynamic threshold alerts
- **Activity Log**: Real-time event tracking with timeline

### Demo Controls
- **Simulate High Load**: Gradually degrade service metrics
- **Simulate Incident**: Complete service outage scenario
- **Reset Metrics**: Return to healthy state

### Enterprise Features
- Beautiful, modern UI with smooth animations
- Real-time metrics updates
- Application Insights integration ready
- Responsive design for all devices

## 🚀 Quick Start - Deploy to Azure

### Step 1: Prepare Your GitHub Repository

1. Create a new GitHub repository (e.g., `aiops-demo-webapp`)
2. Clone this repository locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/aiops-demo-webapp.git
   cd aiops-demo-webapp
   ```
3. Copy all files from this project to your repository
4. Commit and push:
   ```bash
   git add .
   git commit -m "Initial commit: AIOps Demo Dashboard"
   git push origin main
   ```

### Step 2: Create an Azure Static Web App

1. **Open Azure Portal**: https://portal.azure.com
2. **Create a Static Web App**:
   - Click "Create a resource"
   - Search for "Static Web App"
   - Click "Create"

3. **Fill in the basics**:
   - **Resource Group**: Create new or select existing (e.g., `AIOps-Demo-RG`)
   - **Name**: Give it a name (e.g., `aiops-demo-app`)
   - **Plan Type**: Choose "Free"
   - **Region**: Select your closest region

4. **Connect GitHub**:
   - Click "Sign in with GitHub"
   - Authorize Azure
   - Select your organization, repository, and branch (main)

5. **Build Configuration**:
   - **Build Presets**: Select "Custom"
   - **App location**: `.` (dot - root directory)
   - **Output location**: `.` (dot - root directory)
   - Leave "API location" empty (no backend for this demo)

6. **Review and Create**:
   - Click "Review + Create"
   - Click "Create"
   - Wait for deployment to complete (3-5 minutes)

7. **Access Your App**:
   - Once deployed, you'll get a URL: `https://your-app.azurestaticapps.net`
   - Click the URL to view your dashboard!

## 📊 Step 3: Enable Application Insights (Optional but Recommended)

1. **Create an Application Insights resource**:
   - In Azure Portal, search for "Application Insights"
   - Click "Create"
   - Link it to your resource group

2. **Get your Instrumentation Key**:
   - Copy the Instrumentation Key from Application Insights
   - Replace `YOUR_INSTRUMENTATION_KEY_HERE` in `index.html` with your key

3. **Redeploy**:
   - Commit the change to GitHub
   - GitHub Actions will automatically redeploy

## 🔍 Step 4: Configure Monitoring & Alerts

### Create an Availability Test (SLI)

1. Go to your **Application Insights** resource
2. Click **Availability** in the left menu
3. Click **+ Add Standard test**
4. Configure:
   - **Test name**: `Global Availability Check`
   - **URL**: Your Static Web App URL
   - **Test frequency**: 5 minutes
   - **Test locations**: Select London, Tokyo, US East (or others)
   - **Success criteria**: HTTP status 200
5. Click **Create**

### Create Static Threshold Alert

1. Go to **Alerts** in Application Insights
2. Click **+ New alert rule**
3. Configure:
   - **Condition**: Availability < 90%
   - **Action Group**: Create new
   - **Name**: Availability Alert
   - **Notification type**: Email
   - Your email
4. Click **Create alert rule**

### Create Dynamic Threshold Alert

1. Go to **Alerts** in Application Insights
2. Click **+ New alert rule**
3. Configure:
   - **Condition**: Failed requests
   - **Alert rule name**: Failed Requests (Dynamic)
   - **Signal name**: Failed requests
   - **Alert logic**: Dynamic Threshold
   - **Threshold severity**: High
   - **Evaluation period**: Last 30 days
4. Click **Create**

## 🎬 How to Run the Demo

### Scenario 1: Demonstrate Monitoring (5 minutes)

1. Open your dashboard
2. Show the healthy metrics
3. Show the Application Map in Application Insights
4. Explain SLIs and SLOs

### Scenario 2: Simulate Incident (10 minutes)

1. Click **"Simulate Incident"** button
2. Watch:
   - Service status changes to Critical
   - Metrics degrade
   - Activity log shows timeline of detection
   - Alerts fire (both static and dynamic)
3. Explain:
   - **MTTD (Mean Time to Detect)**: Notice how fast the system detected the problem
   - **Static Alerts**: Traditional approach - "If availability < 90%, alert"
   - **Dynamic Alerts**: AI approach - Detects abnormal pattern, not just a number
   - **RCA (Root Cause Analysis)**: Application Insights would show the failure pattern

### Scenario 3: High Load (5 minutes)

1. Click **"Simulate High Load"** button
2. Observe gradual degradation
3. Watch CPU and error rate increase
4. See dynamic alerts trigger on abnormal patterns
5. Click **"Reset Metrics"** to recover

## 📁 Project Structure

```
aiops-demo-webapp/
├── index.html                 # Main dashboard UI
├── app.js                     # Metrics simulation & interactivity
├── staticwebapp.config.json   # Azure Static Web App configuration
└── README.md                  # This file
```

## 💡 Key Concepts Demonstrated

### SLI (Service Level Indicator)
- **Definition**: Metric measuring actual service performance
- **In this demo**: Availability percentage, response time
- **Example**: "Our service is 99.9% available"

### SLO (Service Level Objective)
- **Definition**: Target value for the SLI
- **In this demo**: Availability SLO target of 99.5%
- **Example**: "We aim for 99.5% availability"

### MTTD (Mean Time to Detect)
- **Definition**: Average time to detect a failure
- **In this demo**: Shows as 12s for healthy, drops to 2-5s when incident happens
- **Enterprise goal**: Reduce from minutes to seconds

### Dynamic Thresholds (AIOps)
- **Traditional approach**: Static rule - "Alert if error rate > 5%"
- **Problem**: Ignores normal variations (Mondays have more errors)
- **AIOps approach**: AI learns normal pattern, alerts on abnormal deviations
- **Benefit**: Fewer false positives, faster detection

### Application Map
- **What it is**: Visual graph of your system and dependencies
- **Enterprise feature**: Shows which component is failing
- **In this demo**: Described in event log during incidents

## 🔧 Customization

### Change App Title
Edit `index.html` line 7:
```html
<title>Your Custom Title - Enterprise Service Monitor</title>
```

### Adjust Metrics
Edit `app.js` and modify the `updateMetrics()` function values.

### Change Colors
Edit the CSS gradient in `index.html`:
```css
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
```

### Add Your Logo
Add in the header section:
```html
<img src="your-logo.png" alt="Logo" style="height: 50px; margin-right: 20px;">
```

## 📱 Browser Compatibility

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers supported

## 🔐 Security Notes

- This is a **static app** with no backend
- No sensitive data is stored
- Application Insights can be configured with the real instrumentation key
- For production, implement proper authentication

## 🐛 Troubleshooting

### App not loading?
- Clear browser cache
- Check browser console for errors (F12)
- Verify Static Web App deployment status

### Application Insights not collecting data?
- Replace `YOUR_INSTRUMENTATION_KEY_HERE` with real key
- Wait 1-2 minutes for data to appear in Application Insights
- Check Application Insights is in same region

### Metrics not updating?
- Check browser console for JavaScript errors
- Verify JavaScript is enabled
- Refresh the page

## 📚 Learning Resources

- [Azure Static Web Apps Documentation](https://learn.microsoft.com/en-us/azure/static-web-apps/)
- [Application Insights Overview](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview)
- [SLI/SLO Primer by Google](https://sre.google/books/)
- [Azure AIOps Documentation](https://learn.microsoft.com/en-us/azure/azure-monitor/)

## 🎓 Training Guide

Use this demo in your training to show:

1. **What is Observability?** 
   - Show the dashboard → Explain MELT (Metrics, Events, Logs, Traces)

2. **SLIs vs SLOs**
   - Point to SLI card → Explain it's actual performance
   - Point to SLO Target → Explain it's the goal

3. **Traditional Alerting Problems**
   - Show static threshold alerts
   - Explain alert fatigue

4. **AIOps Solution**
   - Show dynamic thresholds
   - Run "Simulate Incident" to show how AI detects abnormality

5. **Enterprise Tools in Action**
   - Show Application Map concept
   - Explain how Azure reduces MTTD
   - Show event log as audit trail

## 📄 License

This project is provided for educational purposes. Feel free to modify and use in your training.

## ✉️ Support

For issues or questions:
1. Check the troubleshooting section
2. Review Azure Static Web Apps documentation
3. Check Azure Monitor documentation

---

**Happy Learning! 🚀**

Built for Azure AIOps Training | December 2025
