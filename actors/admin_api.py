from flask import Flask
from flask_restful import Api

from worker import WorkersResource, WorkerResource

app = Flask(__name__)
api = Api(app)

# Resources
api.add_resource(WorkersResource, '/actors/<string:actor_id>/workers')
api.add_resource(WorkerResource, '/actors/<string:actor_id>/workers/<string:ch_name>')

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
