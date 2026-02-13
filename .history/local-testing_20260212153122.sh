#!/bin/bash

  # Start Qdrant                                                                                                                                                                                                               
  docker-compose up -d                                                                                                                                                                                                         
                                                                                                                                                                                                                               
  # Seed KB (requires Qdrant running)                                                                                                                                                                                          
  ./scripts/seed-kb.sh                                                                                                                                                                                                         
                                                                                                                                                                                                                               
  # Run tests                                                                                                                                                                                                                  
  cd operator && cargo test 
  cd ..                                                                                                                                                                                                   
  cd investigator && poetry run pytest
  cd ..                                                                                                                                                                                    
  cd ui && poetry run pytest
  cd ..
  