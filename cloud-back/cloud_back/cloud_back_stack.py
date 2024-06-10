from aws_cdk import (
    # Duration,
    Stack,
    aws_apigateway as apigateway,
    aws_lambda as _lambda,
    aws_dynamodb as dynamodb,
    aws_iam as iam, BundlingOptions, Duration,
    # aws_sqs as sqs,
    aws_dynamodb as dynamodb,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_s3 as s3, aws_lambda_event_sources, RemovalPolicy
)
from constructs import Construct

class CloudBackStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        bucket = s3.Bucket(
            self, "ContentBucket-New",
            bucket_name="content-bucket-cloud-app-movie2",

            cors=[
                s3.CorsRule(
                    allowed_methods=[
                        s3.HttpMethods.GET,
                        s3.HttpMethods.PUT,
                        s3.HttpMethods.POST,
                        s3.HttpMethods.DELETE,
                        s3.HttpMethods.HEAD
                    ],
                    allowed_origins=["*"],
                    allowed_headers=["*"]
                )
            ],
            removal_policy=RemovalPolicy.DESTROY
        )

        s3_role = iam.Role(
            self, "S3AccessRole",
            assumed_by=iam.ServicePrincipal("s3.amazonaws.com")  # Postavljamo uslugu koja može koristiti ovu ulogu
        )

        # Dodavanje politike za dozvolu za pristup S3 bucketu
        s3_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                ],
                resources=[
                    "arn:aws:s3:::content-bucket-cloud-app-movie2/*"

                ]
            )
        )
        #
        # bucket_policy_statement = iam.PolicyStatement(
        #     effect=iam.Effect.ALLOW,
        #     actions=[
        #         "s3:GetObject",
        #         "s3:PutObject",
        #         "s3:DeleteObject"
        #     ],
        #     resources=[bucket.bucket_arn + "/*"],
        #     principals=[iam.AnyPrincipal()]
        # )
        #
        #
        # # Dodajemo politiku na S3 kantu
        # bucket.add_to_resource_policy(bucket_policy_statement)


        table = dynamodb.Table(
            self, 'MoviesTable',
            table_name='MoviesTable',
            partition_key={'name': 'movie_id', 'type': dynamodb.AttributeType.STRING},
            sort_key={'name': 'title', 'type': dynamodb.AttributeType.STRING},
            stream=dynamodb.StreamViewType.NEW_IMAGE
        )

        lambda_role = iam.Role(
            self, "LambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
        )
        lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
        )
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:DescribeTable",
                    "dynamodb:Query",
                    "dynamodb:Scan",
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem",
                    "s3:GetObject",
                    "s3:PutObject",
                ],
                resources=[table.table_arn]
            )
        )

        def create_lambda_function(id,name, handler, include_dir, method, layers, database_dynamo,database_s3):
            env='TABLE_NAME'
            if database_dynamo is not None:
                database=database_dynamo
            else:
                env='BUCKET_NAME'
                database=database_s3
            function = _lambda.Function(
                self, id,
                function_name=name,
                runtime=_lambda.Runtime.PYTHON_3_9,
                layers=layers,
                handler=handler,
                code=_lambda.Code.from_asset(include_dir,
                                             # bundling=BundlingOptions(
                                             #     image=_lambda.Runtime.PYTHON_3_9.bundling_image,
                                             #     command=[
                                             #          "cmd.exe", "/c",  # Koristimo cmd.exe za pokretanje komandi na Windows-u
                                             # "pip install --no-cache -r requirements.txt -t . && copy .\\* ..\\asset-output"
                                             #     ],
                                             # ),
                                             ),
                memory_size=128,
                timeout=Duration.seconds(10),
                environment={
                    env: database
                },
                role=lambda_role
            )

            return function

        def upload_lambda_function(id, name, handler, include_dir, method, layers, database_dynamo, database_s3):

            function = _lambda.Function(
                self, id,
                function_name=name,
                runtime=_lambda.Runtime.PYTHON_3_9,
                layers=layers,
                handler=handler,
                code=_lambda.Code.from_asset(include_dir,
                                             # bundling=BundlingOptions(
                                             #     image=_lambda.Runtime.PYTHON_3_9.bundling_image,
                                             #     command=[
                                             #          "cmd.exe", "/c",  # Koristimo cmd.exe za pokretanje komandi na Windows-u
                                             # "pip install --no-cache -r requirements.txt -t . && copy .\\* ..\\asset-output"
                                             #     ],
                                             # ),
                                             ),
                memory_size=128,
                timeout=Duration.seconds(10),
                environment={
                    "TABLE_NAME": database_dynamo,
                    "BUCKET_NAME": database_s3
                },
                role=lambda_role
            )

            return function


        get_movie_lambda = create_lambda_function(
            "getMovies",
            "getMoviesFuction",
            "getMovies.lambda_handler",
            "getMovies",
            "GET",
            [],
            table.table_name,
            None
        )

        download_movie_lambda = upload_lambda_function(
            "getS3Content",
            "downloadContentS3",
            "downloadMovie.download_movie_handler",
            "downloadMovie",
            "GET",
            [],
            table.table_name,
            bucket.bucket_name
        )



        upload_data=upload_lambda_function(
            "postMoviesS3Bucket",
            "postMoviesFunction",
            "upload_data.upload_data_handler",
            "uploadMovies",
            "POST",
            [],
            table.table_name,
            bucket.bucket_name
        )

        upload_data.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                ],
                resources=[
                    f"arn:aws:s3:::content-bucket-cloud-app-movie2/*",  # Dozvole za sve objekte unutar bucketa
                ]))

        download_movie_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                ],
                resources=[
                    f"arn:aws:s3:::content-bucket-cloud-app-movie2/*",  # Dozvole za sve objekte unutar bucketa
                ]))


        api_gateway_role = iam.Role(self, "ApiGatewayRole",
                                    assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
                                    description="Role for API Gateway to invoke lambda functions")


        # Dodaj potrebne permisije roli
        api_gateway_role.add_to_policy(iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=["*"]  # mogu ovde stativi specificirane lambde
        ))

        bucket.grant_read_write(upload_data)

        # Dodavanje dozvola Lambda funkciji za pristup DynamoDB tabeli
        table.grant_read_data(get_movie_lambda)

        bucket.grant_read_write(download_movie_lambda)


        self.api = apigateway.RestApi(self, "CloudProjectTeam14",
                                 rest_api_name="CloudProject2023",
                                 description="This service serves movie contents.",
                                 endpoint_types=[apigateway.EndpointType.REGIONAL],
                                 default_cors_preflight_options={
                                     "allow_origins": apigateway.Cors.ALL_ORIGINS,
                                     "allow_methods": apigateway.Cors.ALL_METHODS
                                 },

                                 )



        get_movie_lambda.add_permission(
            "ApiGatewayInvokePermission",
            action="lambda:InvokeFunction",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            source_arn=self.api.arn_for_execute_api("/*/*/*")
        )

        download_movie_lambda.add_permission(
            "ApiGatewayInvokePermission",
            action="lambda:InvokeFunction",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            source_arn=self.api.arn_for_execute_api("/*/*/*")
        )

        movie_resource = self.api.root.add_resource("movieNew")

        # GET metoda za /movies123
        get_movies_integration = apigateway.LambdaIntegration(get_movie_lambda, credentials_role=api_gateway_role, proxy=True)
        self.api.root.add_resource("movies123").add_method("GET", get_movies_integration)

        # POST metoda za /movie
        movie_resource = self.api.root.add_resource("movie")
        movie_resource.add_method("POST", apigateway.LambdaIntegration(upload_data, credentials_role=api_gateway_role, proxy=True))

        # POST metoda za /movieS3
        self.api.root.add_resource("movieS3").add_method("POST", apigateway.LambdaIntegration(upload_data, credentials_role=api_gateway_role, proxy=True))

        # GET metoda za /movie/{movieId}
        movie_resource_with_id = movie_resource.add_resource("{movieName}")
        movie_resource_with_id.add_method("GET", apigateway.LambdaIntegration(download_movie_lambda,
                                                                              credentials_role=api_gateway_role,
                                                                              proxy=True))

        # GET metoda za /downloadS3Content/{contentId}
        download_s3_resource_with_id = self.api.root.add_resource("downloadS3Content")
        download_s3_resource_with_id_with_id = download_s3_resource_with_id.add_resource("{contentName}")
        download_s3_resource_with_id_with_id.add_method("GET", apigateway.LambdaIntegration(download_movie_lambda,
                                                                                            credentials_role=api_gateway_role,
                                                                                            proxy=True))

        new_rute = self.api.root.add_resource("getFromS3")
        new_rute_id = new_rute.add_resource("{id}")
        new_rute_id.add_method("GET", apigateway.LambdaIntegration(download_movie_lambda, proxy=True))

        # deployment nakon dodavanja svih resursa i metoda
        api_deployment_new = apigateway.Deployment(self, "ApiDeploymentTotalNew",
                                                   api=self.api)

        # novi stage
        apigateway.Stage(self, "NewStage",
                         deployment=api_deployment_new,
                         stage_name="noviStage")