import pytest

from app.api.routes.lottery_draws import LotteryDrawService

# source is mandatory for all successful draw creation requests.
# Existing authorization-denial tests intentionally remain source-free where
# authorization is expected to fail before request-body validation.
