from config import config

def get_wandb_env():
    wandb = config.get("wandb", {}).get("apikey")
    if wandb is None:
        wandb = ""
    else:
        wandb = " WANDB_API_KEY=" + wandb + " "
    return wandb