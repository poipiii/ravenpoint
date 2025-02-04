import json
import os
import numpy as np
import pandas as pd
import sqlite3
import time

from flask import Blueprint, request, jsonify, send_from_directory,Response 
from flask_mail import Mail
from flask_mail import Message

from flask_restx import Namespace, Resource, fields
from project import db, app
from project.utils import get_all_table_names, get_all_relationships, parse_odata_filter, \
  parse_odata_query, validate_create_update_query, validate_delete_query, \
  validate_create_update_query_listname, validate_delete_query_listname, validate_file_query
from werkzeug.exceptions import BadRequest

# Create blueprint
api = Blueprint(
  'api', __name__,
  template_folder='api_templates'
)

app.config['MAIL_SERVER']='localhost'
app.config['MAIL_PORT'] = 1025

mail = Mail(app)

# Connection string
conn_string = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')




# Create namespace
api_namespace = Namespace('_api', 'RavenPoint REST API endpoints')

# Hello world example
hello_world_model = api_namespace.model(
  'Hello World', {
    'message': fields.String(
      readonly=True,
      description='Hello World test example.'
    )
  }
)

hello_world_example = {'message': 'Hello World!'}

@api_namespace.route('')
class HelloWorld(Resource):

  @api_namespace.marshal_list_with(hello_world_model)
  @api_namespace.response(500, 'Internal Server Error')
  def get(self):
    '''Hello world message endpoint'''
    return hello_world_example

# Token endpoint
@api_namespace.route(
  '/contextinfo',
  doc={'description': '''Endpoint for getting X-Request digest value, which is \
    used in POST requests for creating, updating, and deleting entries.'''}
)
class XRequestDigestValue(Resource):
  @api_namespace.response(500, 'Internal Server Error')
  def post(self):
    '''X-Request Digest Value endpoint'''
    return {
      "FormDigestValue": "1111-2222-3333-4444",
      "other": "metadata"
    }

# Endpoint for list metadata
@api_namespace.route(
  "/web/Lists(guid'<string:list_id>')",
  doc={'description': '''Endpoint for getting List metadata. Use `$select` to choose \
    specific metadata fields to retrieve. Options are `Id`, `ListItemEntityTypeFullName`, \
    `table_name` (RavenPoint only) and `table_db_name` (RavenPoint only).'''}
)
@api_namespace.doc(params={'list_id': 'Simulated SP List ID'})
class ListMetadata(Resource):
  @api_namespace.response(200, 'Success: Returns List metadata')
  @api_namespace.response(400, 'Bad request: Invalid query.')
  @api_namespace.response(500, 'Internal Server Error')
  
  def get(self, list_id):
    '''RavenPoint list metadata endpoint'''
    print(request.args.items())
    # Check if list exists
    with sqlite3.connect(conn_string) as conn:
      all_tables = get_all_table_names(conn)
    if list_id not in all_tables.id.tolist():
      raise BadRequest('List does not exist.')
    
    # Extract URL params
    params = {'listId': list_id}
    for k, v in request.args.items():
      if k not in ['$select', '$filter', '$expand', '$top']:
        raise BadRequest('Invalid keyword. Use only $select, $filter, or $expand.')
      params[k] = v
    
    # Get metadata
    table = all_tables \
        .rename(columns={'id': 'Id'}) \
        .loc[all_tables.id.eq(list_id)].to_dict('records')[0]
    table_pascal = table['table_db_name'].title().replace('_', '')
    table['ListItemEntityTypeFullName'] = f'SP.Data.{table_pascal}ListItem'

    # Return all if no specified fields specified
    if '$select' not in params.keys():
        return {'d': table}
    
    # Extract requested fields
    fields = params['$select'].split(',')
    fields = [field.strip() for field in fields]
    if any([field not in ['ListItemEntityTypeFullName', 'Id', 'table_name', 'table_db_name'] for field in fields]):
      raise BadRequest('Invalid metadata property. Options: ListItemEntityTypeFullName, Id, table_name, table_db_name.')
    
    output  = {'Id': table['Id']}
    for field in fields:
      output[field] = table[field]

    return {'d': output}


# Endpoint for list metadata by GetByTitle
@api_namespace.route(
  "/web/lists/GetByTitle('<string:list_name>')",
  doc={'description': '''Endpoint for getting List metadata. Use `$select` to choose \
    specific metadata fields to retrieve. Options are `Id`, `ListItemEntityTypeFullName`, \
    `table_name` (RavenPoint only) and `table_db_name` (RavenPoint only).'''}
)
@api_namespace.doc(params={'list_name': 'Simulated SP List Name'})
class ListByTitleMetadata(Resource):
  @api_namespace.response(200, 'Success: Returns List metadata')
  @api_namespace.response(400, 'Bad request: Invalid query.')
  @api_namespace.response(500, 'Internal Server Error')
  
  def get(self, list_name):
    '''RavenPoint list metadata endpoint'''
    print(request.args.items())
    # Check if list exists
    with sqlite3.connect(conn_string) as conn:
      all_tables = get_all_table_names(conn)
    if list_name not in all_tables.table_name.tolist():
      raise BadRequest('List does not exist.')
    
    # Extract URL params
    params = {'listTitle': list_name}
    for k, v in request.args.items():
      if k not in ['$select', '$filter', '$expand', '$top']:
        raise BadRequest('Invalid keyword. Use only $select, $filter, or $expand.')
      params[k] = v
    
    # Get metadata
    table = all_tables \
        .rename(columns={'id': 'Id'}) \
        .loc[all_tables.table_name.eq(list_name)].to_dict('records')[0]
    table_pascal = table['table_db_name'].title().replace('_', '')
    table['ListItemEntityTypeFullName'] = f'SP.Data.{table_pascal}ListItem'

    # Return all if no specified fields specified
    if '$select' not in params.keys():
        return {'d': table}
    
    # Extract requested fields
    fields = params['$select'].split(',')
    fields = [field.strip() for field in fields]
    if any([field not in ['ListItemEntityTypeFullName', 'Id', 'table_name', 'table_db_name'] for field in fields]):
      raise BadRequest('Invalid metadata property. Options: ListItemEntityTypeFullName, Id, table_name, table_db_name.')
    
    output  = {'Id': table['Id']}
    for field in fields:
      output[field] = table[field]

    return {'d': output}

# Endpoint for getting list items
lietfn_model = api_namespace.model(
  'ListItemEntityTypeFullName', {
    'type': fields.String(description='Appropriate ListItemEntityTypeFullName for the required list')
  }
)

objective_model = api_namespace.model(
  'Objective', {
    '__metadata': fields.Nested(lietfn_model),
    'Title': fields.String(description='Objective title'),
    'objectiveDescription': fields.String(description='Objective description'),
    'objectiveStartDate': fields.String(description='Objective start date in ISO date format'),
    'objectiveEndDate': fields.String(description='Objective end date in ISO date format'),
    'owner': fields.String(description='Staff assigned to objective'),
    'team': fields.String(description='Team owning the objective'),
    'frequency': fields.String(description='Monthly, quarterly, or annual'),
  }
)

keyresult_model = api_namespace.model(
  'Key Result', {
    '__metadata': fields.Nested(lietfn_model),
    'Title': fields.String(description='Key Result title'),
    'krDescription': fields.String(description='Key Result description'),
    'krStartDate': fields.String(description='Key Result start date in ISO date format'),
    'krEndDate': fields.String(description='Key Result end date in ISO date format'),
    'minValue': fields.Integer(description='Starting value'),
    'maxValue': fields.Integer(description='Target value'),
    'currentValue': fields.Integer(description='Current value'),
    'parentObjective': fields.Integer(description='ID of parent Objective')
  }
)

update_model = api_namespace.model(
  'Update', {
    '__metadata': fields.Nested(lietfn_model),
    'Title': fields.String(description='LEAVE THIS BLANK'),
    'updateDate': fields.String(description='Update date in ISO date format'),
    'updateText': fields.String(description='Body of update'),
    'parentKrId': fields.Integer(description='ID of parent Key Result')
  }
)

create_update_model = api_namespace.model(
  'Create/Update Data (choose appropriate model)', {
    'objective': fields.Nested(objective_model),
    'keyresult': fields.Nested(keyresult_model),
    'update': fields.Nested(update_model),
  }
)

@api_namespace.route(
  "/web/Lists(guid'<string:list_id>')/items",
  doc={'description': '''Endpoint for retrieving List items. \
Currently implemented URL params: `select`, `expand`, and `filter`.

- Use `$select=ListItemEntityTypeFullName` to get the List item entity type.
- Use `$select=<columns>` to select columns.
- Use `$expand=<lookup_table>` to join tables.
- Use `$filter=<criteria>` to filter items.

The URL parameter hierarchy is `select` > `expand` > `filter`. Any other combination may result in an error.

**Notes for POST requests:**

1. URL params are ignored.
2. An X-RequestDigest value is required. Click the lock to input a value - any value will pass.
3. The provided payload is for reference only. Choose one of the provided first-level \
keys as the schema and fill in your own values. Check the models below for more details.
  '''})
@api_namespace.doc(params={'list_id': 'Simulated SP List ID'})
class ListItems(Resource):
  @api_namespace.response(200, 'Success: Returns requested list items or properties.')
  @api_namespace.response(400, 'Bad request: Invalid query.')
  @api_namespace.response(500, 'Internal Server Error')
  def get(self, list_id):
    '''RavenPoint list items endpoint (Read)'''
    # time.sleep(2)
    
    # Check for invalid keywords
    request_keys = request.args.keys()
    if any([key not in ['$select', '$filter', '$expand', '$top'] for key in request_keys]):
      raise BadRequest('Invalid keyword(s). Use only $select, $filter, or $expand.')
    
    # Extract URL params
    params = parse_odata_query(request.args)
    if params:
      params['listId'] = list_id

    # Check if list exists; get all relationships
    with sqlite3.connect(conn_string) as conn:
      all_tables = get_all_table_names(conn)
      all_rships = get_all_relationships(conn)
    if list_id not in all_tables.id.tolist():
      raise BadRequest('List does not exist.')

    # Extract table metadata
    curr_table = all_tables.loc[all_tables.id.eq(list_id)].to_dict('records')[0]
    curr_db_table = curr_table['table_db_name']
    # Extract table
    with sqlite3.connect(conn_string) as conn:
        df = pd.read_sql(f"SELECT * FROM {curr_db_table}", conn)
    
    # If no params are given, return all data
    if '$select' not in request_keys and '$filter' not in request_keys and '$expand' not in request_keys:
      return {
        'listId': list_id,
        'value': df.to_dict('records')
      }
    
    # EXPAND - Get all tables in query
    joins = {}
    for col in params['expand_cols']:
      # Check if the column to expand was included in the selected columns
      if not any([col in join_col for join_col in params['join_cols']]):
        raise BadRequest(f"The query to field '{col}' is not valid. The $select query string must specify the target fields and the $expand query string must contain {col}.")
      
      # Check if relationship exists
      rship = all_rships.loc[all_rships.table_left.eq(curr_db_table) & \
        all_rships.table_left_on.eq(col)].to_dict('records')
      if len(rship) == 0:
        raise BadRequest(f"Relationship from field '{col}' does not exist.")
      else:
        joins[col] = {
          'table': rship[0]['table_lookup'],
          'table_pk': rship[0]['table_lookup_on'],
          'is_multi': rship[0]['is_multi']
        }
        print(joins)

    # Process joins data
    for i, col in enumerate(params['join_cols']):
      lookup_col, lookup_table_col = col.split('/')
      if not lookup_col in params['expand_cols']:
        raise BadRequest(f'Lookup field {lookup_col} not specified in $expand parameter.')
      params['join_cols'][i] = params['join_cols'][i].replace(
        lookup_col + '/', joins[lookup_col]['table'] + '.'
      ) + f" AS '{lookup_col}__{lookup_table_col}'"

    # Process filter
    params['filter_query'] = parse_odata_filter(params['filter_query'], joins, curr_db_table)

    # Add aliases to lookup tables
    select_aliases = [f"{curr_db_table}.{col}" for col in params['main_cols']] + \
      params['join_cols']
    
    # Prepare SQL query
    sql_query = []
    sql_query.append(f"SELECT {', '.join(select_aliases)}")
    sql_query.append(f"FROM {curr_db_table}")

    # If single lookup, do a left join; otherwise, left join the junction table first
    multi_cols = []
    for expand_col, lookup_data in joins.items():
      lookup_table = lookup_data['table']
      if lookup_data['is_multi'] == 0:
        sql_query.append(f"LEFT JOIN {lookup_data['table']}" + \
          f" ON {curr_db_table}.{expand_col} = {lookup_data['table']}.{lookup_data['table_pk']}")
      else:
        junction_table = f"{curr_db_table}_{lookup_data['table']}"
        multi_cols.append(expand_col)
        sql_query.append(
          f"LEFT JOIN {junction_table} " + 
          f"ON {curr_db_table}.Id = {junction_table}.{curr_db_table}_pk " +
          f"LEFT JOIN {lookup_table} " +
          f"ON {junction_table}.{lookup_table}_pk = {lookup_table}.Id"
        )

    if params['filter_query']:
      sql_query.append(f"WHERE {params['filter_query']}")

    # Query database and process data
    with sqlite3.connect(conn_string) as conn:
      data = pd.read_sql(' '.join(sql_query), con=conn)
    nested_cols = data.columns[data.columns.str.contains('__', regex=False)]
    nested_cols = list(set([col.split('__')[0] for col in nested_cols]))
    nested_cols = [col for col in nested_cols if not col in multi_cols]

    # Function to handle Id and Title
    def clean_id_and_title(value):
      if pd.isnull(value) or value is None:
        return ''
      if type(value) in [float, int]:
        return int(value)
      if type(value) == str:
        return str(value)

    # Process multi-lookup columns first
    if len(multi_cols) > 0:
      for multi_col in multi_cols:
        sub_cols = data.columns[data.columns.str.contains(multi_col + '__')]
        data[multi_col] = data[sub_cols].apply(lambda x: {k.replace(f'{multi_col}__', ''): clean_id_and_title(v) for k, v in zip(x.index, x.values)}, axis=1)
        data = data.drop(sub_cols, axis=1)
    
      # Merge multi-lookup values
      merge_cols = [col for col in data.columns if not col in multi_cols]
      data = data.groupby(merge_cols).agg(lambda x: x.tolist()).reset_index()
      for multi_col in multi_cols:
        data[multi_col] = data[multi_col].apply(lambda x: [] if all([elem['Id'] == '' for elem in x]) else x)
    
    # Process single lookup columns
    for nested_col in nested_cols:
      sub_cols = data.columns[data.columns.str.contains(nested_col + '__')]
      data[nested_col] = data[sub_cols].apply(lambda x: {k.replace(f'{nested_col}__', ''): clean_id_and_title(v) for k, v in zip(x.index, x.values)}, axis=1)
      data = data.drop(sub_cols, axis=1)

    # Update diagnostic params
    params['sql_query'] = ' '.join(sql_query)
    params['joins'] = joins

    # Allow cross-origin
    output = {
      'diagnostics': params,
      'value': data.replace({np.nan: None}).to_dict('records')
    }

    return output
  
  # Update item
  @api_namespace.expect(create_update_model, validate=False)
  @api_namespace.doc(security='X-RequestDigest')
  def post(self, list_id):
    '''RavenPoint List items endpoint (Create)'''

    # Extract request headers, and body
    headers = request.headers
    data = request.json

    # Run checks
    check_reqs = validate_create_update_query(headers, data, list_id)
    if check_reqs.get('BadRequest'):
      raise BadRequest(check_reqs.get('BadRequest'))
    
    # Get data types
    df = check_reqs['data']
    df = df.drop('Id', axis=1)
    dtypes_lookup = df.dtypes.astype(str).to_dict()

    # Prepare INSERT query
    colnames = []
    values_clause = []
    for k, v in data.items():
      if k in ['Id', '__metadata']:
        continue
      # Convert implicit lookup column Id
      if (len(k) > 2) and ('/' not in k) and (k[-2:] == 'Id') and (k != 'parentKrId'):
        k = k[:-2]
      data_type = dtypes_lookup.get(k, 'object')
      colnames.append(k)
      values_clause.append(f"{v}" if ('int' in data_type or 'float' in data_type) else f"'{v}'")
    query = f'''INSERT INTO {check_reqs.get('table')} ({', '.join(colnames)}) \
VALUES ({', '.join(values_clause)})'''

    # Run update
    with sqlite3.connect(conn_string) as conn:
      cursor = conn.cursor()
      try:
        cursor.execute(query)
        Id = cursor.lastrowid
        conn.commit()
      except Exception as e:
        print(e)
        conn.rollback()
        raise BadRequest(f'Invalid request - data does not match table schema: {e}')
    return {
      # 'data': data,
      # 'token': headers.get('X-RequestDigest'),
      # 'table': check_reqs.get('table'),
      'query': query,
      "d": {'Id': Id},
      'message': f'Successfully added item.',
    }

@api_namespace.route(
  "/web/Lists(guid'<string:list_id>')/items(<string:item_id>)",
  doc={'description': '''Endpoint for updating List items.'''})
@api_namespace.doc(params={
  'list_id': 'Simulated SP List ID',
  'item_id': 'Item to update'
})

class UpdateListItems(Resource):
  # Update item
  @api_namespace.expect(create_update_model, validate=False)
  @api_namespace.doc(security='X-RequestDigest')
  def post(self, list_id, item_id):
    '''RavenPoint list items endpoint (Update/Delete)'''
    # Extract request headers, and body
    headers = request.headers
    data = request.json

    # Update query
    if headers.get('X-Http-Method') == 'MERGE':
      # Run checks on List, ListItemEntityTypeFullName, and item
      check_reqs = validate_create_update_query(headers, data, list_id, True, item_id)
      if check_reqs.get('BadRequest'):
        raise BadRequest(check_reqs.get('BadRequest'))
      
      # Get data types
      df = check_reqs['data']
      df = df.drop('Id', axis=1)
      dtypes_lookup = df.dtypes.astype(str).to_dict()

      # Prepare UPDATE query
      set_clause = []
      for k, v in data.items():
        if k in ['Id', '__metadata']:
          continue
        # Convert implicit lookup column Id
        if (len(k) > 2) and ('/' not in k) and (k[-2:] == 'Id') and (k != 'parentKrId'):
          k = k[:-2]
        data_type = dtypes_lookup.get(k, 'object')
        set_clause.append(f"{k} = {v}" if ('int' in data_type or 'float' in data_type) else f"{k} = '{v}'")
      query = f'''UPDATE {check_reqs.get('table')} \
  SET {', '.join(set_clause)} \
  WHERE Id = {item_id}'''

      # Run update
      with sqlite3.connect(conn_string) as conn:
        cursor = conn.cursor()
        try:
          cursor.execute(query)
          conn.commit()
        except Exception as e:
          conn.rollback()
          raise BadRequest(f'Invalid request - data does not match table schema: {e}')
      return {
        # 'data': data,
        # 'token': headers.get('X-RequestDigest'),
        # 'table': check_reqs.get('table'),
        # 'query': query,
        'message': f'Successfully updated item {item_id}',
      }
    else:
      # Run checks on List, ListItemEntityTypeFullName, and item
      check_reqs = validate_delete_query(headers, list_id, item_id)
      if check_reqs.get('BadRequest'):
        raise BadRequest(check_reqs.get('BadRequest'))

      # Create query
      query = f'''DELETE FROM {check_reqs.get('table')} WHERE Id = {item_id}'''
      # Run update
      with sqlite3.connect(conn_string) as conn:
        cursor = conn.cursor()
        try:
          cursor.execute(query)
          conn.commit()
        except Exception as e:
          conn.rollback()
          raise BadRequest(f'Invalid request - could not delete item: {e}')
      return {
        # 'data': data,
        # 'token': headers.get('X-RequestDigest'),
        # 'table': check_reqs.get('table'),
        # 'query': query,
        'message': f'Successfully delete item {item_id}',
      }


@api_namespace.route(
  "/web/lists/GetByTitle('<string:list_name>')/items",
  doc={'description': '''Endpoint for retrieving List items. \
Currently implemented URL params: `select`, `expand`, and `filter`.

- Use `$select=ListItemEntityTypeFullName` to get the List item entity type.
- Use `$select=<columns>` to select columns.
- Use `$expand=<lookup_table>` to join tables.
- Use `$filter=<criteria>` to filter items.

The URL parameter hierarchy is `select` > `expand` > `filter`. Any other combination may result in an error.

**Notes for POST requests:**

1. URL params are ignored.
2. An X-RequestDigest value is required. Click the lock to input a value - any value will pass.
3. The provided payload is for reference only. Choose one of the provided first-level \
keys as the schema and fill in your own values. Check the models below for more details.
  '''})
@api_namespace.doc(params={'list_name': 'Simulated SP List ID'})
class ListByTitleItems(Resource):
  @api_namespace.response(200, 'Success: Returns requested list items or properties.')
  @api_namespace.response(400, 'Bad request: Invalid query.')
  @api_namespace.response(500, 'Internal Server Error')
  def get(self, list_name):
    '''RavenPoint list items endpoint (Read)'''
    # time.sleep(2)
    
    # Check for invalid keywords
    request_keys = request.args.keys()
    if any([key not in ['$select', '$filter', '$expand', '$top'] for key in request_keys]):
      raise BadRequest('Invalid keyword(s). Use only $select, $filter, or $expand.')
    
    # Extract URL params
    params = parse_odata_query(request.args)
    if params:
      params['listTitle'] = list_name

    # Check if list exists; get all relationships
    with sqlite3.connect(conn_string) as conn:
      all_tables = get_all_table_names(conn)
      all_rships = get_all_relationships(conn)
    if list_name not in all_tables.table_name.tolist():
      raise BadRequest('List does not exist.')

    # Extract table metadata
    curr_table = all_tables.loc[all_tables.table_name.eq(list_name)].to_dict('records')[0]
    curr_db_table = curr_table['table_db_name']

    # Extract table
    with sqlite3.connect(conn_string) as conn:
        df = pd.read_sql(f"SELECT * FROM {curr_db_table}", conn)
    
    # If no params are given, return all data
    if '$select' not in request_keys and '$filter' not in request_keys and '$expand' not in request_keys:
      return {
        'listTitle': list_name,
        'value': df.to_dict('records')
      }
    
    # EXPAND - Get all tables in query
    joins = {}
    print('tables to join',joins)
    for col in params['expand_cols']:
      # Check if the column to expand was included in the selected columns
      if not any([col in join_col for join_col in params['join_cols']]):
        raise BadRequest(f"The query to field '{col}' is not valid. The $select query string must specify the target fields and the $expand query string must contain {col}.")
      
      # Check if relationship exists
      print(col)
      print('all_rships',all_rships)
      print(all_rships.loc[all_rships.table_left.eq(curr_db_table) & \
        all_rships.table_left_on.eq(col)].to_dict('records'))
      rship = all_rships.loc[all_rships.table_left.eq(curr_db_table) & \
        all_rships.table_left_on.eq(col)].to_dict('records')
      if len(rship) == 0 or rship == []:
        raise BadRequest(f"Relationship from field '{col}' does not exist.")
      else:
        joins[col] = {
          'table': rship[0]['table_lookup'],
          'table_pk': rship[0]['table_lookup_on'],
          'is_multi': rship[0]['is_multi']
        }

    # Process joins data
    for i, col in enumerate(params['join_cols']):
      lookup_col, lookup_table_col = col.split('/')
      if not lookup_col in params['expand_cols']:
        raise BadRequest(f'Lookup field {lookup_col} not specified in $expand parameter.')
      params['join_cols'][i] = params['join_cols'][i].replace(
        lookup_col + '/', joins[lookup_col]['table'] + '.'
      ) + f" AS '{lookup_col}__{lookup_table_col}'"

    # Process filter
    params['filter_query'] = parse_odata_filter(params['filter_query'], joins, curr_db_table)

    # Add aliases to lookup tables
    select_aliases = [f"{curr_db_table}.{col}" for col in params['main_cols']] + \
      params['join_cols']
    if not select_aliases :
      select_aliases = ["*"]
    print("",select_aliases)
    # Prepare SQL query
    sql_query = []
    sql_query.append(f"SELECT {', '.join(select_aliases)}")
    sql_query.append(f"FROM {curr_db_table}")

    # If single lookup, do a left join; otherwise, left join the junction table first
    multi_cols = []
    for expand_col, lookup_data in joins.items():
      lookup_table = lookup_data['table']
      if lookup_data['is_multi'] == 0:
        sql_query.append(f"LEFT JOIN {lookup_data['table']}" + \
          f" ON {curr_db_table}.{expand_col} = {lookup_data['table']}.{lookup_data['table_pk']}")
      else:
        junction_table = f"{curr_db_table}_{lookup_data['table']}"
        multi_cols.append(expand_col)
        sql_query.append(
          f"LEFT JOIN {junction_table} " + 
          f"ON {curr_db_table}.Id = {junction_table}.{curr_db_table}_pk " +
          f"LEFT JOIN {lookup_table} " +
          f"ON {junction_table}.{lookup_table}_pk = {lookup_table}.Id"
        )

    if params['filter_query']:
      sql_query.append(f"WHERE {params['filter_query']}")

    # Query database and process data
    print("conn tr",conn_string)
    with sqlite3.connect(conn_string) as conn:
      print(' '.join(sql_query))
      data = pd.read_sql(' '.join(sql_query), con=conn)
    nested_cols = data.columns[data.columns.str.contains('__', regex=False)]
    nested_cols = list(set([col.split('__')[0] for col in nested_cols]))
    nested_cols = [col for col in nested_cols if not col in multi_cols]

    # Function to handle Id and Title
    def clean_id_and_title(value):
      if pd.isnull(value) or value is None:
        return ''
      if type(value) in [float, int]:
        return int(value)
      if type(value) == str:
        return str(value)

    # Process multi-lookup columns first
    if len(multi_cols) > 0:
      for multi_col in multi_cols:
        sub_cols = data.columns[data.columns.str.contains(multi_col + '__')]
        data[multi_col] = data[sub_cols].apply(lambda x: {k.replace(f'{multi_col}__', ''): clean_id_and_title(v) for k, v in zip(x.index, x.values)}, axis=1)
        data = data.drop(sub_cols, axis=1)
    
      # Merge multi-lookup values
      merge_cols = [col for col in data.columns if not col in multi_cols]
      data = data.groupby(merge_cols).agg(lambda x: x.tolist()).reset_index()
      for multi_col in multi_cols:
        data[multi_col] = data[multi_col].apply(lambda x: [] if all([elem['Id'] == '' for elem in x]) else x)
    
    # Process single lookup columns
    for nested_col in nested_cols:
      sub_cols = data.columns[data.columns.str.contains(nested_col + '__')]
      data[nested_col] = data[sub_cols].apply(lambda x: {k.replace(f'{nested_col}__', ''): clean_id_and_title(v) for k, v in zip(x.index, x.values)}, axis=1)
      data = data.drop(sub_cols, axis=1)

    # Update diagnostic params
    params['sql_query'] = ' '.join(sql_query)
    params['joins'] = joins

    # Allow cross-origin
    output = {
      'diagnostics': params,
      'value': data.replace({np.nan: None}).to_dict('records')
    }

    return output
  
  # Update item
  @api_namespace.expect(create_update_model, validate=False)
  @api_namespace.doc(security='X-RequestDigest')
  def post(self, list_name):
    '''RavenPoint List items endpoint (Create)'''

    # Extract request headers, and body
    headers = request.headers
    data = request.json

    # Run checks
    check_reqs = validate_create_update_query_listname(headers, data, list_name)
    if check_reqs.get('BadRequest'):
      raise BadRequest(check_reqs.get('BadRequest'))
    
    # Get data types
    df = check_reqs['data']
    df = df.drop('Id', axis=1)
    dtypes_lookup = df.dtypes.astype(str).to_dict()

    # Prepare INSERT query
    colnames = []
    values_clause = []
    for k, v in data.items():
      if k in ['Id', '__metadata']:
        continue
      # Convert implicit lookup column Id
      if (len(k) > 2) and ('/' not in k) and (k[-2:] == 'Id') and (k != 'parentKrId'):
        k = k[:-2]
      data_type = dtypes_lookup.get(k, 'object')
      colnames.append(k)
      values_clause.append(f"{v}" if ('int' in data_type or 'float' in data_type) else f"'{v}'")
    query = f'''INSERT INTO {check_reqs.get('table')} ({', '.join(colnames)}) \
VALUES ({', '.join(values_clause)})'''

    # Run update
    with sqlite3.connect(conn_string) as conn:
      cursor = conn.cursor()
      try:
        cursor.execute(query)
        Id = cursor.lastrowid
        conn.commit()
        print(Id)
      except Exception as e:
        print(e)
        conn.rollback()
        raise BadRequest(f'Invalid request - data does not match table schema: {e}')
    return {
    #  'data': data,
      # 'token': headers.get('X-RequestDigest'),
      # 'table': check_reqs.get('table'),
      'query': query,
      "d":{'Id':Id,**data},
      'message': f'Successfully added item.',
    }

@api_namespace.route(
  "/web/lists/GetByTitle('<string:list_name>')/items(<string:item_id>)",
  doc={'description': '''Endpoint for updating List items.'''})
@api_namespace.doc(params={
  'list_name': 'Simulated SP List Name',
  'item_id': 'Item to update'
})

class UpdateListItems(Resource):
  # Update item
  @api_namespace.expect(create_update_model, validate=False)
  @api_namespace.doc(security='X-RequestDigest')
  def post(self, list_name, item_id):
    '''RavenPoint list items endpoint (Update/Delete)'''
    # Extract request headers, and body
    headers = request.headers
    
    # Update query
    if headers.get('X-Http-Method') == 'MERGE':
      data = request.json
      # Run checks on List, ListItemEntityTypeFullName, and item
      check_reqs = validate_create_update_query_listname(headers, data, list_name, True, item_id)
      if check_reqs.get('BadRequest'):
        raise BadRequest(check_reqs.get('BadRequest'))
      
      # Get data types
      df = check_reqs['data']
      df = df.drop('Id', axis=1)
      dtypes_lookup = df.dtypes.astype(str).to_dict()

      # Prepare UPDATE query
      set_clause = []
      for k, v in data.items():
        if k in ['Id', '__metadata']:
          continue
        # Convert implicit lookup column Id
        if (len(k) > 2) and ('/' not in k) and (k[-2:] == 'Id') and (k != 'parentKrId'):
          k = k[:-2]
        data_type = dtypes_lookup.get(k, 'object')
        set_clause.append(f"{k} = {v}" if ('int' in data_type or 'float' in data_type) else f"{k} = '{v}'")
      query = f'''UPDATE {check_reqs.get('table')} \
  SET {', '.join(set_clause)} \
  WHERE Id = {item_id}'''

      # Run update
      with sqlite3.connect(conn_string) as conn:
        cursor = conn.cursor()
        try:
          cursor.execute(query)
          Id = cursor.lastrowid
          conn.commit()

        except Exception as e:
          conn.rollback()
          raise BadRequest(f'Invalid request - data does not match table schema: {e}')
      return {
        # 'data': data,
        # 'token': headers.get('X-RequestDigest'),
        # 'table': check_reqs.get('table'),
        # 'query': query,
        "d":{'Id':Id,**data},
        'message': f'Successfully updated item {item_id}',
      }
    else:
      # Run checks on List, ListItemEntityTypeFullName, and item
      check_reqs = validate_delete_query_listname(headers, list_name, item_id)
      if check_reqs.get('BadRequest'):
        raise BadRequest(check_reqs.get('BadRequest'))

      # Create query
      query = f'''DELETE FROM {check_reqs.get('table')} WHERE Id = {item_id}'''
      # Run update
      with sqlite3.connect(conn_string) as conn:
        cursor = conn.cursor()
        try:
          cursor.execute(query)
          conn.commit()
        except Exception as e:
          conn.rollback()
          raise BadRequest(f'Invalid request - could not delete item: {e}')
      return {
        # 'data': data,
        # 'token': headers.get('X-RequestDigest'),
        # 'table': check_reqs.get('table'),
        # 'query': query,
        'message': f'Successfully delete item {item_id}',
      }
    

@api_namespace.route("/web/GetFolderByServerRelativeUrl('Shared Documents')/Files('<string:file_name>')/$value",doc={"description":'''Endpoint for retrieving files form ravenpoint'''})
@api_namespace.doc(params={
  "file_name":"Name of simulated file in ravenpoint"
})

class GetFile(Resource):


  @api_namespace.doc(security='X-RequestDigest')
  def get(self,file_name):
    folder = "/project/data/documents"
    curdir = os.path.abspath(os.getcwd())
    fulldir = curdir.replace('''\\''',"/") + folder
    headers = request.headers
    check_reqs = validate_file_query(headers,file_name)
    if check_reqs.get('BadRequest'):
      raise BadRequest(check_reqs.get('BadRequest'))
    else:
       return send_from_directory(fulldir,file_name)
  

@api_namespace.route("/web/getuserbyid('<int:Id>')",doc={"description":'''Endpoint for retrieving simulated user by id from ravenpoint'''})
@api_namespace.doc(params={
  "Id":"Id of simulated user in ravenpoint"
})
class getuserbyid(Resource):
  @api_namespace.doc(security='X-RequestDigest')
  def get(self,Id):
      with sqlite3.connect(conn_string) as conn:
        try:
          df = pd.read_sql_query("SELECT * FROM rpusers WHERE Id = {}".format(Id),conn)
          data = df.to_dict('records')
          if data == []:
            raise BadRequest(f'User does not exist')
          else:
            return data[0]
        except Exception as e:
          conn.rollback()
          raise BadRequest(f'Error retrieving user {e}')


@api_namespace.route("/web/currentUser",doc={"description":'''Endpoint for retrieving current simulated user from ravenpoint will return first user in rpusers table'''})
class currentUser(Resource):
  @api_namespace.doc(security='X-RequestDigest')
  def get(self):
      with sqlite3.connect(conn_string) as conn:
        try:
          df = pd.read_sql_query("SELECT * FROM rpusers WHERE Id = {}".format(1),conn)
          data = df.to_dict('records')
          if data == []:
            raise BadRequest(f'No users exist in rpusers table please create a user')
          else:
            return data[0]
        except Exception as e:
          conn.rollback()
          raise BadRequest(f'Error retrieving user {e}')
        

@api_namespace.route("/web/SiteUsers",doc={"description":'''Endpoint for retrieving all users in a sharepoint site'''})
class currentUser(Resource):
  @api_namespace.doc(security='X-RequestDigest')
  def get(self):
      # Check for invalid keywords
    list_name = "rpusers"
    request_keys = request.args.keys()
    if any([key not in ['$select', '$filter', '$expand', '$top'] for key in request_keys]):
      raise BadRequest('Invalid keyword(s). Use only $select, $filter, or $expand.')
    
    params = parse_odata_query(request.args)
    if params:
      params['listTitle'] = "rpusers"

    # with sqlite3.connect(conn_string) as conn:
    #   all_tables = get_all_table_names(conn)
    #   all_rships = get_all_relationships(conn)
    # print(curr_table['table_db_name'])
    # if list_name not in all_tables.table_name.tolist():
    #   raise BadRequest('List does not exist.')
    # # Extract table metadata
    # curr_table = all_tables.loc[all_tables.table_name.eq(list_name)].to_dict('records')[0]
    # curr_db_table = curr_table['table_db_name']
    with sqlite3.connect(conn_string) as conn:
      try:
        df = pd.read_sql_query("SELECT * FROM rpusers",conn)
        data = df.to_dict('records')
      except Exception as e:
          conn.rollback()
          raise BadRequest(f'Error retrieving user infomation {e}')
    
    if '$select' not in request_keys and '$filter' not in request_keys and '$expand' not in request_keys:
          return {
        'listTitle': list_name,
        'value': data
      }
    joins = {}
     # Process filter
    params['filter_query'] = parse_odata_filter(params['filter_query'], joins, list_name)
    sql_query = []
    sql_query.append(f"SELECT * ")
    sql_query.append(f"FROM {list_name}")
    if params['filter_query']:
      sql_query.append(f"WHERE {params['filter_query']}")
    print(" ".join(sql_query))
    with sqlite3.connect(conn_string) as conn:
     try:
        df = pd.read_sql_query(" ".join(sql_query),conn)
        data = df.to_dict('records')
        return {
        'listTitle': list_name,
        'value': data
      }
     except Exception as e:
          conn.rollback()
          raise BadRequest(f'Error retrieving user infomation {e}')





@api_namespace.route("/SP.Utilities.Utility.SendEmail",doc={"description":'''Endpoint for simulating sending emails from ravenpoint'''})
class currentUser(Resource):
  @api_namespace.doc(security='X-RequestDigest')
  def post(self):
     headers = request.headers
     data = request.json
     Email_From  = "test@ravenpoint.com"
     Email_To = data["properties"]["To"]["results"]
     Email_Body = data["properties"]["Body"]
     Email_Subject = data["properties"]["Subject"]
     msg = Message(
                  sender=Email_From,
                  recipients=Email_To)
     msg.body = Email_Body
     msg.subject = Email_Subject
     mail.send(msg)
     return "email sent"
     
     

