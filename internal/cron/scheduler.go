package cron

import (
	"log"

	"dev-mcp/internal/git"

	"github.com/robfig/cron/v3"
)

type Scheduler struct {
	cron   *cron.Cron
	syncer *git.Syncer
	expr   string
}

func NewScheduler(syncer *git.Syncer, expr string) (*Scheduler, error) {
	c := cron.New()
	s := &Scheduler{
		cron:   c,
		syncer: syncer,
		expr:   expr,
	}

	_, err := c.AddFunc(expr, func() {
		log.Printf("[cron] Running scheduled git sync (expression: %s)...\n", expr)
		success, commit, out := syncer.PullRepo("cron")
		if !success {
			log.Printf("[cron] Git sync failed: %s (commit: %s)\n", out, commit)
		} else {
			log.Printf("[cron] Git sync succeeded: commit %s\n", commit)
		}
	})
	if err != nil {
		return nil, err
	}

	return s, nil
}

func (s *Scheduler) Start() {
	if s.cron != nil {
		s.cron.Start()
	}
}

func (s *Scheduler) Stop() {
	if s.cron != nil {
		s.cron.Stop()
	}
}
