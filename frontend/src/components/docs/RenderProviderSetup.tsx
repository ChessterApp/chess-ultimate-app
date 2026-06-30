import {
  Card,
  CardContent,
  Typography,
  ListItem,
  List,
  ListItemIcon,
  ListItemText,
  Button,
  Box,
  Chip,
} from "@mui/material";
import {
  Launch as LaunchIcon,
  CheckCircle as CheckCircleIcon,
  Info as InfoIcon,
} from "@mui/icons-material";

import { ProviderConfig } from "@/libs/docs/helper";

// White-label TODO: orphan docs component. When wired into a route, accept
// `appName` from useBranding() and substitute the literal "Chesster" mentions
// (ChessterCloud is a product name and stays literal).
export const renderProviderSetup = (provider: ProviderConfig) => (
  <Card sx={{ mb: 3 }}>
    <CardContent>
      <Typography
        variant="h6"
        gutterBottom
        sx={{ color: "text.primary" }}
      >
        {provider.name} Setup Guide
      </Typography>


    {provider.name === "aginecloud" ? (
        <Box sx={{
          p: 3,
          textAlign: 'center',
          backgroundColor: "background.paper",
          borderRadius: 2,
          borderColor: "success.main",
          borderWidth: 2,
          borderStyle: "solid",
        }}>
          <CheckCircleIcon sx={{
            fontSize: 48,
            color: "success.main",
            mb: 2
          }} />
          <Typography variant="h6" sx={{ color: "text.primary", mb: 1 }}>
            No Setup Required!
          </Typography>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            ChessterCloud models are completely free and ready to use immediately.
            Just select a model and start analyzing your chess games.
            ChessterCloud is in beta, so you might experiece few delays
          </Typography>
        </Box>
      ) : provider.name === "Ollama" ? (
        <List dense>
          <ListItem>
            <ListItemIcon>
              <CheckCircleIcon sx={{ color: "success.main" }} />
            </ListItemIcon>
            <ListItemText primary="Download Ollama" />
            <Button
              variant="outlined"
              size="small"
              color="success"
              startIcon={<LaunchIcon />}
              href="https://ollama.com/"
              target="_blank"
              rel="noopener noreferrer"
              sx={{ ml: 2 }}
            >
              Download
            </Button>
          </ListItem>

          <ListItem>
            <ListItemIcon>
              <CheckCircleIcon sx={{ color: "success.main" }} />
            </ListItemIcon>
            <ListItemText primary="Sign up to Ollama" />
          </ListItem>

          <ListItem>
            <ListItemIcon>
              <CheckCircleIcon sx={{ color: "success.main" }} />
            </ListItemIcon>
            <ListItemText primary="Install models locally using terminal or use cloud (-cloud models) in Ollama interface by chatting with them" />
          </ListItem>

          <ListItem>
            <ListItemIcon>
              <CheckCircleIcon sx={{ color: "success.main" }} />
            </ListItemIcon>
            <ListItemText primary="Download Ngrok" />
            <Button
              variant="outlined"
              size="small"
              color="success"
              startIcon={<LaunchIcon />}
              href="https://ngrok.com/download/"
              target="_blank"
              rel="noopener noreferrer"
              sx={{ ml: 2 }}
            >
              Download
            </Button>
          </ListItem>

          <ListItem>
            <ListItemIcon>
              <CheckCircleIcon sx={{ color: "success.main" }} />
            </ListItemIcon>
            <ListItemText primary="Authenticate ngrok in terminal by getting the token from in your dashboard" />
            <Button
              variant="outlined"
              size="small"
              color="success"
              startIcon={<LaunchIcon />}
              href="https://dashboard.ngrok.com/ "
              target="_blank"
              rel="noopener noreferrer"
              sx={{ ml: 2 }}
            >
              Open Dashboard
            </Button>
          </ListItem>

          <ListItem>
            <ListItemIcon>
              <CheckCircleIcon sx={{ color: "success.main" }} />
            </ListItemIcon>
            <ListItemText primary="Point ngrok to port 11434 by running ngrok http 11434" />
          </ListItem>

          <ListItem>
            <ListItemIcon>
              <CheckCircleIcon sx={{ color: "success.main" }} />
            </ListItemIcon>
            <ListItemText primary="Paste the ngrok web link in Chesster settings" />
          </ListItem>

          <ListItem>
            <ListItemIcon>
              <CheckCircleIcon sx={{ color: "success.main" }} />
            </ListItemIcon>
            <ListItemText primary="Start using it!" />
          </ListItem>
        </List>
      ) : (
        <List dense>
          <ListItem>
            <ListItemIcon>
              <CheckCircleIcon sx={{ color: "success.main" }} />
            </ListItemIcon>
            <ListItemText primary="Visit the API keys page" />
          </ListItem>
          <ListItem sx={{ pl: 4 }}>
            <Button
              variant="outlined"
              size="small"
              color="success"
              startIcon={<LaunchIcon />}
              href={provider.website}
              target="_blank"
              rel="noopener noreferrer"
            >
              Get API Key
            </Button>
          </ListItem>

          <ListItem>
            <ListItemIcon>
              <CheckCircleIcon sx={{ color: "success.main" }} />
            </ListItemIcon>
            <ListItemText primary="Create a new API key" />
          </ListItem>

          <ListItem>
            <ListItemIcon>
              <CheckCircleIcon sx={{ color: "success.main" }} />
            </ListItemIcon>
            <ListItemText
              primary="Copy your API key"
              secondary={`Should start with: ${provider.keyPrefix}...`}
            />
          </ListItem>

          <ListItem>
            <ListItemIcon>
              <CheckCircleIcon sx={{ color: "success.main" }} />
            </ListItemIcon>
            <ListItemText primary="Enter the key in Chesster settings" />
          </ListItem>
        </List>
      )}

      <Box sx={{ mt: 2 }}>
        <Typography variant="subtitle2" gutterBottom color="secondary">
          Available Models:
        </Typography>
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
          {provider.models.map((model) => (
            <Chip
              key={model}
              label={model}
              size="small"
              variant="outlined"
              sx={{
                color: "text.primary",
                borderColor: "text.secondary",
              }}
            />
          ))}
        </Box>
      </Box>

      <Box sx={{ mt: 2 }}>
        <Button
          variant="text"
          size="small"
          color="success"
          startIcon={<InfoIcon />}
          href={provider.docsUrl}
          target="_blank"
          rel="noopener noreferrer"
        >
          View Documentation
        </Button>
      </Box>
    </CardContent>
  </Card>
);
