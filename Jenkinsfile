
pipeline {

    agent any

    environment {

        PROJECT_DIR = "/opt/apple-music"

        EC2_PUBLIC_IP = "65.2.127.100"

        POSTGRES_USER = "musicuser"

        POSTGRES_PASSWORD = credentials('apple-music-db-password')

        DB_NAME = "musicdb"

        BACKEND_PORT = "8000"

        FRONTEND_PORT = "80"
    }

    stages {

        stage('Checkout') {
            steps {

                echo "======================================"
                echo "CHECKOUT SOURCE CODE"
                echo "======================================"

                checkout scm
            }
        }


        stage('Copy Project') {
            steps {

                echo "======================================"
                echo "COPY PROJECT TO DEPLOYMENT DIRECTORY"
                echo "======================================"

                sh '''
                    mkdir -p ${PROJECT_DIR}

                    cp -r ${WORKSPACE}/. ${PROJECT_DIR}/

                    echo "Project copied successfully"
                '''
            }
        }


        stage('Create Environment File') {
            steps {

                echo "======================================"
                echo "CREATING ENVIRONMENT FILE"
                echo "======================================"

                sh '''
                    cd ${PROJECT_DIR}

                    cat > .env <<EOF
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=${DB_NAME}

DATABASE_URL=postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${DB_NAME}

R2_ENDPOINT=
R2_ACCESS_KEY=
R2_SECRET_KEY=
R2_BUCKET=
EOF

                    chmod 600 .env

                    echo "Environment file created successfully"
                '''
            }
        }


        stage('Validate Docker Compose') {
            steps {

                echo "======================================"
                echo "VALIDATING DOCKER COMPOSE"
                echo "======================================"

                sh '''
                    cd ${PROJECT_DIR}

                    docker compose config -q

                    echo "Docker Compose configuration is valid"
                '''
            }
        }


        stage('Build Docker Images') {
            steps {

                echo "======================================"
                echo "BUILDING DOCKER IMAGES"
                echo "======================================"

                sh '''
                    cd ${PROJECT_DIR}

                    docker compose build --no-cache

                    echo "Docker images built successfully"
                '''
            }
        }


        stage('Deploy Application') {
            steps {

                echo "======================================"
                echo "DEPLOYING APPLICATION"
                echo "======================================"

                sh '''
                    cd ${PROJECT_DIR}

                    docker compose up -d

                    echo "Application deployment initiated"
                '''
            }
        }


        stage('Check Containers') {
            steps {

                echo "======================================"
                echo "CHECKING CONTAINERS"
                echo "======================================"

                sh '''
                    cd ${PROJECT_DIR}

                    sleep 10

                    docker compose ps

                    echo ""
                    echo "Container status checked"
                '''
            }
        }


        stage('Backend Health Check') {
            steps {

                echo "======================================"
                echo "BACKEND HEALTH CHECK"
                echo "======================================"

                sh '''
                    echo "Testing FastAPI backend through Nginx..."

                    curl --retry 10 \
                         --retry-delay 5 \
                         --retry-connrefused \
                         -f http://localhost/api/health

                    echo ""

                    echo "Backend is working successfully"
                '''
            }
        }


        stage('Frontend Health Check') {
            steps {

                echo "======================================"
                echo "FRONTEND HEALTH CHECK"
                echo "======================================"

                sh '''
                    echo "Testing frontend..."

                    curl --retry 10 \
                         --retry-delay 5 \
                         --retry-connrefused \
                         -I -f http://localhost:${FRONTEND_PORT}

                    echo ""

                    echo "Frontend is working successfully"
                '''
            }
        }


        stage('Deployment Information') {
            steps {

                echo "======================================"
                echo "DEPLOYMENT COMPLETED"
                echo "======================================"

                echo "Application:"
                echo "http://${EC2_PUBLIC_IP}"

                echo ""

                echo "Backend API:"
                echo "http://${EC2_PUBLIC_IP}/api/health"

                echo ""

                echo "Swagger:"
                echo "http://${EC2_PUBLIC_IP}/api/docs"

                echo ""

                echo "Albums API:"
                echo "http://${EC2_PUBLIC_IP}/api/albums"

                echo ""

                echo "Jenkins:"
                echo "http://${EC2_PUBLIC_IP}:8080"

                echo "======================================"
            }
        }
    }


    post {

        success {

            echo """
========================================
       APPLE MUSIC DEPLOYMENT SUCCESS
========================================

Application:
http://${EC2_PUBLIC_IP}

Backend Health:
http://${EC2_PUBLIC_IP}/api/health

Swagger:
http://${EC2_PUBLIC_IP}/api/docs

Albums:
http://${EC2_PUBLIC_IP}/api/albums

========================================
"""
        }


        failure {

            echo """
========================================
       APPLE MUSIC DEPLOYMENT FAILED
========================================

Run these commands on EC2:

cd ${PROJECT_DIR}

docker compose ps

docker compose logs --tail=100

docker logs apple-music-db

docker logs apple-music-backend

docker logs apple-music-frontend

========================================
"""
        }

        always {

            echo "Apple Music Jenkins pipeline execution completed."
        }
    }
}
